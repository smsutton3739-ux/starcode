"""FastAPI dependencies: authentication, authorisation, rate limiting, audit."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import rate_limit
from app.core.logging import current_request_id, get_logger
from app.core.security import AuthError, decode_token, hash_ip
from app.db.models.ops import AuditAction, AuditLog
from app.db.models.user import Role, User
from app.db.session import get_db

logger = get_logger(__name__)

# auto_error=False so anonymous requests reach the handler; the homepage must work
# without an account.
bearer_scheme = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user_optional(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> User | None:
    if credentials is None or not credentials.credentials:
        return None
    try:
        payload = decode_token(credentials.credentials, expected_kind="access")
    except AuthError:
        # An invalid token on an optional-auth route is treated as anonymous rather than
        # as an error, so an expired token never blocks a public page.
        return None

    user = db.get(User, payload["sub"])
    if user is None or not user.is_active:
        return None
    return user


def get_current_user(
    user: Annotated[User | None, Depends(get_current_user_optional)],
) -> User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to use this endpoint.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def _require(minimum: Role):
    def dependency(user: Annotated[User, Depends(get_current_user)]) -> User:
        if not user.role.at_least(minimum):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"This action requires the {minimum.value} role or higher; "
                    f"your account has {user.role.value}."
                ),
            )
        return user

    return dependency


require_user = _require(Role.USER)
require_researcher = _require(Role.RESEARCHER)
require_moderator = _require(Role.MODERATOR)
require_admin = _require(Role.ADMIN)

CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_current_user_optional)]
AdminUser = Annotated[User, Depends(require_admin)]
ModeratorUser = Annotated[User, Depends(require_moderator)]


def as_utc(value: datetime) -> datetime:
    """Coerce a datetime to timezone-aware UTC.

    Not every backend round-trips tzinfo: SQLite stores no offset and returns naive
    datetimes, and some Postgres columns can too. Comparing a naive value against an
    aware `now()` raises TypeError, which in an authorisation check would turn a routine
    expiry comparison into a 500. Values from this application are always written as UTC,
    so attaching the offset back is correct rather than a guess.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def client_ip(request: Request) -> str:
    """Client address, honouring X-Forwarded-For only for its first entry.

    Behind a trusted proxy this is the real client. Do not deploy without a proxy that
    overwrites this header, or a caller can spoof it and evade per-IP limits.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limiter(bucket: str, cost: int = 1):
    """Per-route rate limiting keyed by user id when signed in, IP otherwise."""

    def dependency(
        request: Request,
        user: Annotated[User | None, Depends(get_current_user_optional)] = None,
    ) -> None:
        identity = f"user:{user.id}" if user else f"ip:{client_ip(request)}"
        limit = rate_limit.limit_for_role(user.role.value if user else None)
        result = rate_limit.check(identity, bucket, limit)

        request.state.rate_limit_headers = result.headers()

        if not result.allowed:
            logger.warning("rate_limit.exceeded", bucket=bucket, identity=identity)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Rate limit reached ({result.limit} per hour). "
                    + (
                        f"Try again in {result.retry_after} seconds."
                        if not user
                        else f"Try again in {result.retry_after} seconds, or contact an "
                        "administrator if you need a higher limit."
                    )
                    + ("" if user else " Signing in raises this limit substantially.")
                ),
                headers=result.headers(),
            )

    return dependency


def record_audit(
    db: Session,
    action: AuditAction,
    *,
    actor: User | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    outcome: str = "success",
    request: Request | None = None,
    detail: dict | None = None,
) -> None:
    """Write an audit entry. Never raises — a logging failure must not fail the request
    that caused it, but it is logged loudly."""
    try:
        db.add(
            AuditLog(
                created_at=datetime.now(UTC),
                action=action,
                actor_id=actor.id if actor else None,
                actor_email=actor.email if actor else None,
                target_type=target_type,
                target_id=target_id,
                outcome=outcome,
                ip_hash=hash_ip(client_ip(request)) if request else None,
                user_agent=(request.headers.get("user-agent", "")[:500] if request else None),
                request_id=current_request_id(),
                detail=detail or {},
            )
        )
        db.flush()
    except Exception as exc:  # noqa: BLE001
        logger.error("audit.write_failed", action=action.value, error=str(exc))


def get_anonymous_token(
    x_analysis_token: Annotated[str | None, Header(alias="X-Analysis-Token")] = None,
) -> str | None:
    """Capability token letting an anonymous submitter read back their own analysis."""
    return x_analysis_token


def paginate(limit: int = 20, offset: int = 0) -> tuple[int, int]:
    return max(1, min(limit, 100)), max(0, offset)


def get_owned_or_shared_analysis(
    db: Session,
    analysis_id: str,
    user: User | None,
    anonymous_token: str | None,
):
    """Fetch an analysis the caller is entitled to read, or raise 404.

    Deliberately returns 404 rather than 403 for an analysis that exists but is not
    theirs: a 403 confirms the id is real, which leaks the existence of other users'
    work to anyone who can guess or enumerate ids.
    """
    from app.core.security import can_access_analysis, verify_token_hash
    from app.db.models.analysis import Analysis

    analysis = db.get(Analysis, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="No such analysis.")

    if can_access_analysis(
        owner_id=analysis.owner_id,
        user_id=user.id if user else None,
        user_role=user.role if user else None,
    ):
        return analysis

    if (
        analysis.owner_id is None
        and anonymous_token
        and analysis.anonymous_token_hash
        and verify_token_hash(anonymous_token, analysis.anonymous_token_hash)
    ):
        return analysis

    # Fall back to an active share token supplied as the anonymous token header.
    if anonymous_token:
        from app.db.models.content import Share

        shares = db.execute(select(Share).where(Share.analysis_id == analysis_id)).scalars().all()
        now = datetime.now(UTC)
        for share in shares:
            if share.revoked_at is not None:
                continue
            if share.expires_at is not None and as_utc(share.expires_at) < now:
                continue
            if verify_token_hash(anonymous_token, share.token_hash):
                share.view_count += 1
                db.commit()
                return analysis

    raise HTTPException(status_code=404, detail="No such analysis.")


__all__ = [
    "DbSession",
    "CurrentUser",
    "OptionalUser",
    "AdminUser",
    "ModeratorUser",
    "get_current_user",
    "get_current_user_optional",
    "require_user",
    "require_researcher",
    "require_moderator",
    "require_admin",
    "rate_limiter",
    "record_audit",
    "client_ip",
    "get_anonymous_token",
    "paginate",
    "get_owned_or_shared_analysis",
]
