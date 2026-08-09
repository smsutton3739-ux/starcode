"""Shared Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.items) < self.total


class PaginationParams(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class Message(BaseModel):
    message: str
    detail: str | None = None


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    request_id: str | None = None
    field_errors: dict[str, list[str]] | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    database: str
    ai_provider: dict[str, Any]
    checks: dict[str, Any] = Field(default_factory=dict)


class ClaimTypeInfo(BaseModel):
    value: str
    label: str
    short: str
    description: str
    tone: str


class TimestampedModel(ORMModel):
    id: str
    created_at: datetime
    updated_at: datetime


__all__ = [
    "ORMModel",
    "Page",
    "PaginationParams",
    "Message",
    "ErrorResponse",
    "HealthResponse",
    "ClaimTypeInfo",
    "TimestampedModel",
]
