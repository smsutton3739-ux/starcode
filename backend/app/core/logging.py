"""Structured logging with request-scoped correlation IDs."""

from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Any

import structlog

from app.core.config import settings

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_user_id: ContextVar[str | None] = ContextVar("user_id", default=None)
_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)


def new_request_id() -> str:
    return uuid.uuid4().hex


def bind_request_context(
    request_id: str | None = None,
    user_id: str | None = None,
    trace_id: str | None = None,
) -> None:
    if request_id is not None:
        _request_id.set(request_id)
    if user_id is not None:
        _user_id.set(user_id)
    if trace_id is not None:
        _trace_id.set(trace_id)


def current_request_id() -> str | None:
    return _request_id.get()


def current_trace_id() -> str | None:
    return _trace_id.get()


def _inject_context(_logger: Any, _name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    for key, var in (("request_id", _request_id), ("user_id", _user_id), ("trace_id", _trace_id)):
        value = var.get()
        if value:
            event_dict.setdefault(key, value)
    return event_dict


_REDACT_KEYS = {
    "password",
    "secret",
    "token",
    "api_key",
    "authorization",
    "access_token",
    "refresh_token",
    "client_secret",
}


def _redact(_logger: Any, _name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Defence in depth: never let a credential reach the log sink."""
    for key in list(event_dict):
        if key.lower() in _REDACT_KEYS:
            event_dict[key] = "[redacted]"
    return event_dict


def configure_logging() -> None:
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level, force=True)
    for noisy in ("uvicorn.access", "httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel(max(level, logging.WARNING))

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _inject_context,
        _redact,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if settings.LOG_FORMAT == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "starcode") -> Any:
    return structlog.get_logger(name)


__all__ = [
    "configure_logging",
    "get_logger",
    "bind_request_context",
    "current_request_id",
    "current_trace_id",
    "new_request_id",
]
