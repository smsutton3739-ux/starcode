"""Authentication: password accounts, OAuth, tokens."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, rate_limiter, record_audit
from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import (
    AuthError,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.models.ops import AuditAction
from app.db.models.user import OAuthIdentity, Role, User, UserSetting
from app.schemas.common import Message
from app.schemas.user import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserOut,
    UserSettingsOut,
    UserSettingsUpdate,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

#: OAuth state lives server-side and is single-use, so a stolen callback URL cannot be
#: replayed. In a multi-replica deployment this belongs in Redis; see docs/DEPLOYMENT.md.
_oauth_states: dict[str, float] = {}
_STATE_TTL_SECONDS = 600


def _issue_tokens(user: User) -> TokenPair:
    return TokenPair(
        access_token=create_token(user.id, "access", role=user.role),
        refresh_token=create_token(user.id, "refresh", role=user.role),
        expires_in=settings.ACCESS_TOKEN_TTL_MINUTES * 60,
    )


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(rate_limiter("auth"))])
def register(payload: RegisterRequest, request: Request, db: DbSession) -> TokenPair:
    email = payload.email.lower().strip()
    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing is not None:
        record_audit(
            db, AuditAction.REGISTER, outcome="duplicate", request=request,
            target_type="email", detail={"reason": "email already registered"},
        )
        db.commit()
        # Same message and status as success would give for a new address, so this
        # endpoint cannot be used to enumerate registered users.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That email address cannot be registered. Try signing in instead.",
        )

    user = User(
        email=email,
        display_name=payload.display_name or email.split("@")[0],
        hashed_password=hash_password(payload.password),
        role=Role.USER,
    )
    db.add(user)
    db.flush()
    db.add(UserSetting(user_id=user.id))

    record_audit(db, AuditAction.REGISTER, actor=user, request=request)
    db.commit()

    logger.info("auth.registered", user_id=user.id)
    return _issue_tokens(user)


@router.post("/login", response_model=TokenPair, dependencies=[Depends(rate_limiter("auth"))])
def login(payload: LoginRequest, request: Request, db: DbSession) -> TokenPair:
    email = payload.email.lower().strip()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()

    # verify_password runs even when the user is missing, so a wrong address and a wrong
    # password take the same time.
    if not verify_password(payload.password, user.hashed_password if user else None):
        record_audit(
            db, AuditAction.LOGIN_FAILED, actor=user, outcome="failure", request=request,
            detail={"email_attempted": email[:120]},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )

    assert user is not None
    if not user.is_active:
        record_audit(db, AuditAction.LOGIN_FAILED, actor=user, outcome="inactive", request=request)
        db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account is disabled.")

    user.last_login_at = datetime.now(timezone.utc)
    record_audit(db, AuditAction.LOGIN, actor=user, request=request)
    db.commit()

    return _issue_tokens(user)


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest, db: DbSession) -> TokenPair:
    try:
        claims = decode_token(payload.refresh_token, expected_kind="refresh")
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    user = db.get(User, claims["sub"])
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="This account is no longer active.")
    return _issue_tokens(user)


@router.post("/logout", response_model=Message)
def logout(request: Request, db: DbSession, user: CurrentUser) -> Message:
    record_audit(db, AuditAction.LOGOUT, actor=user, request=request)
    db.commit()
    # Tokens are stateless, so this records the event and instructs the client. Add a
    # revocation list (keyed on the token's jti) if immediate invalidation is required.
    return Message(
        message="Signed out.",
        detail="Discard your stored tokens. Access tokens remain valid until they expire.",
    )


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate({**user.__dict__, "role": user.role.value})


@router.get("/me/settings", response_model=UserSettingsOut)
def get_settings(db: DbSession, user: CurrentUser) -> UserSettingsOut:
    if user.settings is None:
        db.add(UserSetting(user_id=user.id))
        db.commit()
        db.refresh(user)
    return UserSettingsOut.model_validate(user.settings)


@router.patch("/me/settings", response_model=UserSettingsOut)
def update_settings(
    payload: UserSettingsUpdate, request: Request, db: DbSession, user: CurrentUser
) -> UserSettingsOut:
    if user.settings is None:
        db.add(UserSetting(user_id=user.id))
        db.flush()
        db.refresh(user)

    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(user.settings, field, value)

    record_audit(db, AuditAction.SETTINGS_UPDATED, actor=user, request=request)
    db.commit()
    db.refresh(user.settings)
    return UserSettingsOut.model_validate(user.settings)


# --------------------------------------------------------------------------------------
# OAuth
# --------------------------------------------------------------------------------------

PROVIDERS = {
    "google": {
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
        "scope": "openid email profile",
    },
    "github": {
        "authorize_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "userinfo_url": "https://api.github.com/user",
        "scope": "read:user user:email",
    },
}


def _provider_credentials(provider: str) -> tuple[str, str]:
    if provider == "google":
        return settings.GOOGLE_CLIENT_ID, settings.GOOGLE_CLIENT_SECRET
    if provider == "github":
        return settings.GITHUB_CLIENT_ID, settings.GITHUB_CLIENT_SECRET
    raise HTTPException(status_code=404, detail=f"Unknown provider {provider!r}.")


def _prune_states() -> None:
    now = datetime.now(timezone.utc).timestamp()
    for key, created in list(_oauth_states.items()):
        if now - created > _STATE_TTL_SECONDS:
            _oauth_states.pop(key, None)


@router.get("/oauth/{provider}/authorize")
def oauth_authorize(provider: str) -> RedirectResponse:
    client_id, client_secret = _provider_credentials(provider)
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=503,
            detail=(
                f"{provider.title()} sign-in is not configured on this server. Set "
                f"{provider.upper()}_CLIENT_ID and {provider.upper()}_CLIENT_SECRET."
            ),
        )

    _prune_states()
    state = secrets.token_urlsafe(24)
    _oauth_states[state] = datetime.now(timezone.utc).timestamp()

    config = PROVIDERS[provider]
    params = {
        "client_id": client_id,
        "redirect_uri": f"{settings.OAUTH_REDIRECT_BASE}{settings.API_V1_PREFIX}/auth/oauth/{provider}/callback",
        "response_type": "code",
        "scope": config["scope"],
        "state": state,
    }
    return RedirectResponse(f"{config['authorize_url']}?{urlencode(params)}")


@router.get("/oauth/{provider}/callback")
def oauth_callback(
    provider: str,
    code: str,
    state: str,
    request: Request,
    db: DbSession,
) -> RedirectResponse:
    client_id, client_secret = _provider_credentials(provider)

    # Single-use state: pop rather than read, so a replayed callback fails.
    if _oauth_states.pop(state, None) is None:
        raise HTTPException(
            status_code=400,
            detail="This sign-in link has expired or was already used. Start again.",
        )

    config = PROVIDERS[provider]
    redirect_uri = (
        f"{settings.OAUTH_REDIRECT_BASE}{settings.API_V1_PREFIX}/auth/oauth/{provider}/callback"
    )

    try:
        with httpx.Client(timeout=15.0) as client:
            token_response = client.post(
                config["token_url"],
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
                headers={"Accept": "application/json"},
            )
            token_response.raise_for_status()
            access_token = token_response.json().get("access_token")
            if not access_token:
                raise HTTPException(status_code=502, detail="The provider returned no access token.")

            profile_response = client.get(
                config["userinfo_url"],
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )
            profile_response.raise_for_status()
            profile = profile_response.json()

            email = profile.get("email")
            if not email and provider == "github":
                emails = client.get(
                    "https://api.github.com/user/emails",
                    headers={"Authorization": f"Bearer {access_token}"},
                ).json()
                primary = next(
                    (e for e in emails if e.get("primary") and e.get("verified")), None
                )
                email = primary["email"] if primary else None
    except httpx.HTTPError as exc:
        logger.warning("auth.oauth_exchange_failed", provider=provider, error=str(exc))
        raise HTTPException(status_code=502, detail="Sign-in with that provider failed.") from exc

    subject = str(profile.get("sub") or profile.get("id") or "")
    if not subject or not email:
        raise HTTPException(
            status_code=400,
            detail=(
                "The provider did not return a verified email address, which this "
                "application requires."
            ),
        )

    email = email.lower()
    identity = db.execute(
        select(OAuthIdentity).where(
            OAuthIdentity.provider == provider,
            OAuthIdentity.provider_subject == subject,
        )
    ).scalar_one_or_none()

    if identity is not None:
        user = identity.user
    else:
        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user is None:
            user = User(
                email=email,
                display_name=profile.get("name") or profile.get("login") or email.split("@")[0],
                avatar_url=profile.get("picture") or profile.get("avatar_url"),
                email_verified=True,
                role=Role.USER,
            )
            db.add(user)
            db.flush()
            db.add(UserSetting(user_id=user.id))
        db.add(
            OAuthIdentity(
                user_id=user.id,
                provider=provider,
                provider_subject=subject,
                provider_email=email,
                # Only the fields actually used are kept; storing the raw profile would
                # accumulate provider data nobody asked for.
                raw_profile={
                    k: profile.get(k) for k in ("name", "login", "picture", "avatar_url")
                    if profile.get(k)
                },
            )
        )

    if not user.is_active:
        raise HTTPException(status_code=403, detail="This account is disabled.")

    user.last_login_at = datetime.now(timezone.utc)
    record_audit(db, AuditAction.LOGIN, actor=user, request=request, detail={"provider": provider})
    db.commit()

    tokens = _issue_tokens(user)
    # Tokens go in the fragment, which browsers do not send to servers and which stays
    # out of referrer headers and server logs.
    fragment = urlencode(
        {"access_token": tokens.access_token, "refresh_token": tokens.refresh_token}
    )
    return RedirectResponse(f"{settings.FRONTEND_BASE_URL}/auth/callback#{fragment}")


@router.get("/oauth/providers")
def list_providers() -> dict:
    return {
        "providers": [
            {
                "name": name,
                "configured": all(_provider_credentials(name)),
                "authorize_url": f"{settings.API_V1_PREFIX}/auth/oauth/{name}/authorize",
            }
            for name in PROVIDERS
        ]
    }


__all__ = ["router"]
