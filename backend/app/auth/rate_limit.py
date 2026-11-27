"""Atomic Redis-backed login rate limiter with fail-closed production behavior."""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from typing import Protocol

from redis import Redis
from redis.exceptions import RedisError

from app.auth.exceptions import RateLimiterUnavailableError, RateLimitExceededError
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Atomic INCR + conditional EXPIRE on first hit so TTL is never lost on crash.
_ATOMIC_INCR_EXPIRE_LUA = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1]))
end
return current
"""


class RateLimiter(Protocol):
    def check_login_attempt(self, *, client_ip: str, normalized_email: str) -> None: ...


def _derived_key(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]
    return f"auth:rl:{prefix}:{digest}"


class InMemoryRateLimiter:
    """Process-local fixed-window fallback used only outside production."""

    def __init__(self, *, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._buckets: dict[str, tuple[int, float]] = {}

    def _hit(self, key: str) -> int:
        now = time.monotonic()
        with self._lock:
            count, expires_at = self._buckets.get(key, (0, now + self.window_seconds))
            if now >= expires_at:
                count = 0
                expires_at = now + self.window_seconds
            count += 1
            self._buckets[key] = (count, expires_at)
            return count

    def check_login_attempt(self, *, client_ip: str, normalized_email: str) -> None:
        ip_count = self._hit(_derived_key("ip", client_ip or "unknown"))
        acct_count = self._hit(_derived_key("acct", normalized_email))
        if ip_count > self.max_attempts or acct_count > self.max_attempts:
            raise RateLimitExceededError()


class RedisLoginRateLimiter:
    """Atomic Redis rate limiter keyed by hashed IP and hashed normalized email."""

    def __init__(
        self,
        redis_client: Redis,
        *,
        max_attempts: int,
        window_seconds: int,
        fail_closed: bool,
    ) -> None:
        self.redis = redis_client
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.fail_closed = fail_closed
        self._fallback = InMemoryRateLimiter(
            max_attempts=max_attempts,
            window_seconds=window_seconds,
        )

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> RedisLoginRateLimiter:
        current = settings or get_settings()
        client = Redis.from_url(
            current.redis_url,
            decode_responses=True,
            socket_connect_timeout=1.0,
            socket_timeout=1.0,
        )
        return cls(
            client,
            max_attempts=current.auth_login_rate_limit_max_attempts,
            window_seconds=current.auth_login_rate_limit_window_seconds,
            fail_closed=current.app_env == "production",
        )

    def _incr_key(self, key: str) -> int:
        result = self.redis.eval(_ATOMIC_INCR_EXPIRE_LUA, 1, key, str(self.window_seconds))
        return int(result)

    def check_login_attempt(self, *, client_ip: str, normalized_email: str) -> None:
        ip_key = _derived_key("ip", client_ip or "unknown")
        acct_key = _derived_key("acct", normalized_email)
        try:
            ip_count = self._incr_key(ip_key)
            acct_count = self._incr_key(acct_key)
        except RedisError as exc:
            if self.fail_closed:
                logger.error("Redis rate limiter unavailable in production")
                raise RateLimiterUnavailableError() from exc
            logger.warning("Redis rate limiter unavailable; using process-local fallback")
            self._fallback.check_login_attempt(
                client_ip=client_ip,
                normalized_email=normalized_email,
            )
            return

        if ip_count > self.max_attempts or acct_count > self.max_attempts:
            raise RateLimitExceededError()
