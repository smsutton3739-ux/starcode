"""Passwords, tokens, hashing and authorisation primitives."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings
from app.db.models.user import Role

#: Work factor. 12 is roughly 250ms on current server hardware — costly enough to make
#: offline cracking expensive, cheap enough not to become a login DoS vector.
BCRYPT_ROUNDS = 12

#: A real hash of a throwaway value, used to equalise timing when an account has no
#: password set or does not exist. Computed once at import so it costs nothing per call
#: beyond the comparison itself.
_DUMMY_HASH = bcrypt.hashpw(b"timing-equalizer", bcrypt.gensalt(rounds=BCRYPT_ROUNDS))

TokenKind = Literal["access", "refresh"]


class AuthError(Exception):
    """Authentication or authorisation failure."""


# ---- passwords -------------------------------------------------------------------
#
# bcrypt is used directly rather than through passlib: passlib 1.7.4 is unmaintained and
# misdetects bcrypt 4.1+, which makes it reject valid passwords outright.


def hash_password(password: str) -> str:
    # bcrypt silently truncates at 72 bytes, which would make two different long
    # passwords equivalent. Reject rather than truncate.
    encoded = password.encode("utf-8")
    if len(encoded) > 72:
        raise ValueError("Password must be at most 72 bytes.")
    return bcrypt.hashpw(encoded, bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("ascii")


def verify_password(plain: str, hashed: str | None) -> bool:
    encoded = plain.encode("utf-8")[:72]
    if not hashed:
        # Compare against a dummy so a missing account takes the same time as a wrong
        # password, closing a user-enumeration timing side channel.
        bcrypt.checkpw(encoded, _DUMMY_HASH)
        return False
    try:
        return bcrypt.checkpw(encoded, hashed.encode("ascii"))
    except (ValueError, TypeError):
        # A malformed stored hash must fail closed, not raise into the request handler.
        return False


PASSWORD_MIN_LENGTH = 12


def validate_password_strength(password: str) -> list[str]:
    """Length-first policy. Composition rules push users toward predictable
    substitutions; length is what actually resists offline attack."""
    problems: list[str] = []
    if len(password) < PASSWORD_MIN_LENGTH:
        problems.append(f"Password must be at least {PASSWORD_MIN_LENGTH} characters.")
    if len(password.encode("utf-8")) > 72:
        problems.append("Password must be at most 72 bytes.")
    if password.lower() in _COMMON_PASSWORDS:
        problems.append("This password is too common.")
    if len(set(password)) < 5:
        problems.append("Password must use at least 5 distinct characters.")
    return problems


_COMMON_PASSWORDS = frozenset(
    {
        "password", "password123", "123456789012", "qwertyuiop12", "letmein12345",
        "administrator", "starcode1234", "changeme1234", "welcome12345",
    }
)


# ---- JWT -------------------------------------------------------------------------


def create_token(
    subject: str,
    kind: TokenKind = "access",
    *,
    role: Role | None = None,
    extra: dict[str, Any] | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    if expires_delta is None:
        expires_delta = (
            timedelta(minutes=settings.ACCESS_TOKEN_TTL_MINUTES)
            if kind == "access"
            else timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS)
        )
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "nbf": int(now.timestamp()),
        "typ": kind,
        # A unique id per token so a refresh token can be individually revoked.
        "jti": secrets.token_urlsafe(16),
    }
    if role is not None:
        payload["role"] = role.value
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str, expected_kind: TokenKind | None = None) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise AuthError("Invalid or expired token.") from exc

    if expected_kind and payload.get("typ") != expected_kind:
        # Without this check a refresh token would be accepted as an access token,
        # silently granting a 30-day session.
        raise AuthError(f"Expected a {expected_kind} token.")
    if not payload.get("sub"):
        raise AuthError("Token has no subject.")
    return payload


# ---- opaque tokens (shares, anonymous claims) -------------------------------------


def new_opaque_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """Keyed hash, so a database leak alone does not yield usable share links."""
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"), token.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def verify_token_hash(token: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_token(token), stored_hash)


def hash_ip(ip: str | None) -> str | None:
    """Hash an IP for the audit log: enough to correlate abuse, not enough to identify."""
    if not ip:
        return None
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"), ip.encode("utf-8"), hashlib.sha256
    ).hexdigest()[:32]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---- authorisation ---------------------------------------------------------------


def require_role(actual: Role, minimum: Role) -> None:
    if not actual.at_least(minimum):
        raise AuthError(
            f"This action requires the {minimum.value} role or higher; you have {actual.value}."
        )


def can_access_analysis(
    *, owner_id: str | None, user_id: str | None, user_role: Role | None
) -> bool:
    """Ownership, or moderator-and-above. Anonymous analyses (owner_id None) are reached
    only through their capability token, which is checked separately."""
    if owner_id is None:
        return False
    if user_id and owner_id == user_id:
        return True
    return bool(user_role and user_role.at_least(Role.MODERATOR))


__all__ = [
    "AuthError",
    "hash_password",
    "verify_password",
    "validate_password_strength",
    "PASSWORD_MIN_LENGTH",
    "create_token",
    "decode_token",
    "new_opaque_token",
    "hash_token",
    "verify_token_hash",
    "hash_ip",
    "sha256_bytes",
    "require_role",
    "can_access_analysis",
]
