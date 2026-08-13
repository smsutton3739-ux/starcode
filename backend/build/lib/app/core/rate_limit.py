"""Rate limiting with a Redis backend and an in-process fallback.

Fixed-window counters keyed by identity and route class. Redis when available so limits
hold across replicas; an in-process dict otherwise, which is correct for a single worker
and degrades to per-worker limits rather than to no limits at all.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_at: int

    @property
    def retry_after(self) -> int:
        return max(1, self.reset_at - int(time.time()))

    def headers(self) -> dict[str, str]:
        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
            "X-RateLimit-Reset": str(self.reset_at),
        }
        if not self.allowed:
            headers["Retry-After"] = str(self.retry_after)
        return headers


class _InProcessBackend:
    def __init__(self) -> None:
        self._counts: dict[str, tuple[int, int]] = {}
        self._lock = threading.Lock()

    def incr(self, key: str, window: int) -> tuple[int, int]:
        now = int(time.time())
        reset_at = (now // window + 1) * window
        with self._lock:
            count, existing_reset = self._counts.get(key, (0, reset_at))
            if existing_reset <= now:
                count, existing_reset = 0, reset_at
            count += 1
            self._counts[key] = (count, existing_reset)

            # Opportunistic sweep so a long-running process does not accumulate keys
            # for every IP it has ever seen.
            if len(self._counts) > 10_000:
                self._counts = {k: v for k, v in self._counts.items() if v[1] > now}
            return count, existing_reset


class _RedisBackend:
    def __init__(self, url: str) -> None:
        import redis

        self._client = redis.Redis.from_url(url, socket_timeout=1, socket_connect_timeout=1)
        self._client.ping()

    def incr(self, key: str, window: int) -> tuple[int, int]:
        now = int(time.time())
        reset_at = (now // window + 1) * window
        pipe = self._client.pipeline()
        pipe.incr(key)
        pipe.expireat(key, reset_at)
        count = pipe.execute()[0]
        return int(count), reset_at


_backend: _InProcessBackend | _RedisBackend | None = None
_backend_lock = threading.Lock()


def get_backend() -> _InProcessBackend | _RedisBackend:
    global _backend
    if _backend is not None:
        return _backend
    with _backend_lock:
        if _backend is not None:
            return _backend
        if not settings.REDIS_URL.strip():
            # Deliberately unset, which is correct for a single-instance deployment.
            # Reported as a decision rather than a failure: an operator scanning the logs
            # of a working free-tier deployment should not find a warning about a service
            # they chose not to run.
            logger.info(
                "rate_limit.backend",
                backend="in-process",
                note="REDIS_URL is unset; limits are per-process, which is exact on one instance",
            )
            _backend = _InProcessBackend()
            return _backend

        try:
            _backend = _RedisBackend(settings.REDIS_URL)
            logger.info("rate_limit.backend", backend="redis")
        except Exception as exc:  # noqa: BLE001 - any Redis failure falls back
            logger.warning(
                "rate_limit.redis_unavailable",
                error=str(exc),
                note="falling back to in-process counters; limits are per-worker",
            )
            _backend = _InProcessBackend()
        return _backend


def reset_backend() -> None:
    """Used by tests to get a clean slate."""
    global _backend
    with _backend_lock:
        _backend = None


def check(identity: str, bucket: str, limit: int, window: int | None = None) -> RateLimitResult:
    window = window or settings.RATE_LIMIT_WINDOW_SECONDS
    key = f"rl:{bucket}:{identity}:{int(time.time()) // window}"
    try:
        count, reset_at = get_backend().incr(key, window)
    except Exception as exc:  # noqa: BLE001
        # Fail open on backend failure. A rate limiter that takes the site down when
        # Redis blips is a worse outage than the abuse it prevents; the event is logged
        # so it is visible rather than silent.
        logger.error("rate_limit.backend_failure", error=str(exc), bucket=bucket)
        return RateLimitResult(True, limit, limit, int(time.time()) + window)

    return RateLimitResult(
        allowed=count <= limit,
        limit=limit,
        remaining=max(0, limit - count),
        reset_at=reset_at,
    )


def limit_for_role(role_value: str | None) -> int:
    if role_value in ("admin", "moderator"):
        return settings.RATE_LIMIT_ADMIN_PER_HOUR
    if role_value:
        return settings.RATE_LIMIT_USER_PER_HOUR
    return settings.RATE_LIMIT_ANONYMOUS_PER_HOUR


__all__ = ["RateLimitResult", "check", "limit_for_role", "reset_backend", "get_backend"]
