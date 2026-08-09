"""Auth, user and collection schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.security import validate_password_strength
from app.schemas.common import ORMModel


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=200)
    display_name: str | None = Field(default=None, max_length=120)

    @field_validator("password")
    @classmethod
    def _strong_enough(cls, v: str) -> str:
        problems = validate_password_strength(v)
        if problems:
            raise ValueError(" ".join(problems))
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=200)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(ORMModel):
    id: str
    email: str
    display_name: str | None = None
    avatar_url: str | None = None
    role: str
    is_active: bool
    email_verified: bool
    analyses_count: int
    created_at: datetime
    last_login_at: datetime | None = None


class UserSettingsOut(ORMModel):
    theme: str
    default_output_language: str
    show_advanced_by_default: bool
    email_notifications: bool
    preferences: dict[str, Any] = Field(default_factory=dict)


class UserSettingsUpdate(BaseModel):
    theme: str | None = Field(default=None, pattern="^(light|dark|system)$")
    default_output_language: str | None = Field(default=None, max_length=16)
    show_advanced_by_default: bool | None = None
    email_notifications: bool | None = None
    preferences: dict[str, Any] | None = None


class ProjectOut(ORMModel):
    id: str
    name: str
    description: str | None = None
    is_archived: bool
    created_at: datetime


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)


class CollectionOut(ORMModel):
    id: str
    name: str
    description: str | None = None
    is_public: bool
    created_at: datetime
    analysis_count: int = 0


class CollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    is_public: bool = False


class TagOut(ORMModel):
    id: str
    name: str
    slug: str
    color: str | None = None


class ShareCreate(BaseModel):
    expires_in_days: int | None = Field(default=None, ge=1, le=365)
    allow_export: bool = True


class ShareOut(BaseModel):
    id: str
    url: str
    token: str | None = Field(
        default=None,
        description="Shown once at creation. It is stored hashed and cannot be recovered.",
    )
    expires_at: datetime | None = None
    allow_export: bool
    view_count: int
    revoked: bool = False


class NotificationOut(ORMModel):
    id: str
    kind: str
    title: str
    body: str | None = None
    link: str | None = None
    read_at: datetime | None = None
    created_at: datetime


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    mode: str = Field(default="semantic", pattern="^(semantic|keyword|hybrid)$")
    scope: str = Field(default="analyses", pattern="^(analyses|corpus|all)$")
    limit: int = Field(default=20, ge=1, le=100)


class SearchHit(BaseModel):
    kind: str
    id: str
    title: str
    snippet: str
    score: float
    match_strength: str | None = None
    citation: str | None = None
    url: str | None = None
    created_at: datetime | None = None


class SearchResponse(BaseModel):
    query: str
    mode: str
    scope: str
    total: int
    hits: list[SearchHit]
    note: str | None = None


class RoleUpdate(BaseModel):
    role: str = Field(pattern="^(viewer|user|researcher|moderator|admin)$")


class AuditLogOut(ORMModel):
    id: str
    created_at: datetime
    action: str
    actor_id: str | None = None
    actor_email: str | None = None
    target_type: str | None = None
    target_id: str | None = None
    outcome: str
    request_id: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "RegisterRequest",
    "LoginRequest",
    "TokenPair",
    "RefreshRequest",
    "UserOut",
    "UserSettingsOut",
    "UserSettingsUpdate",
    "ProjectOut",
    "ProjectCreate",
    "CollectionOut",
    "CollectionCreate",
    "TagOut",
    "ShareCreate",
    "ShareOut",
    "NotificationOut",
    "SearchRequest",
    "SearchHit",
    "SearchResponse",
    "RoleUpdate",
    "AuditLogOut",
]
