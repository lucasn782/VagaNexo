"""Atomic Redis-backed multi-scope rate limiter with fail-closed production behavior."""

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
    def check_login_allowed(self, *, client_ip: str, normalized_email: str) -> None: ...
    def record_login_failure(self, *, client_ip: str, normalized_email: str) -> None: ...
    def record_login_success(self, *, client_ip: str, normalized_email: str) -> None: ...
    def check_rate_limit(
        self,
        *,
        scope: str,
        key_value: str,
        max_attempts: int,
        window_seconds: int,
    ) -> None: ...
    def check_login_attempt(self, *, client_ip: str, normalized_email: str) -> None: ...


def _derived_key(scope: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]
    return f"auth:rl:{scope}:{digest}"


def _acct_ip_value(normalized_email: str, client_ip: str) -> str:
    return f"{normalized_email}|{client_ip or 'unknown'}"


class InMemoryRateLimiter:
    """Process-local fixed-window fallback used only outside production."""

    def __init__(
        self,
        *,
        max_attempts: int = 5,
        window_seconds: int = 300,
        ip_max_attempts: int | None = None,
    ) -> None:
        self.max_attempts = max_attempts
        self.ip_max_attempts = ip_max_attempts if ip_max_attempts is not None else max_attempts
        self.acct_global_max_attempts = max(max_attempts * 4, self.ip_max_attempts)
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._buckets: dict[str, tuple[int, float]] = {}

    def _peek(self, key: str) -> int:
        now = time.monotonic()
        with self._lock:
            entry = self._buckets.get(key)
            if entry is None:
                return 0
            count, expires_at = entry
            if now >= expires_at:
                self._buckets.pop(key, None)
                return 0
            return count

    def _hit(self, key: str, *, window_seconds: int | None = None) -> int:
        ttl = window_seconds if window_seconds is not None else self.window_seconds
        now = time.monotonic()
        with self._lock:
            count, expires_at = self._buckets.get(key, (0, now + ttl))
            if now >= expires_at:
                count = 0
                expires_at = now + ttl
            count += 1
            self._buckets[key] = (count, expires_at)
            return count

    def _clear(self, key: str) -> None:
        with self._lock:
            self._buckets.pop(key, None)

    def check_login_allowed(self, *, client_ip: str, normalized_email: str) -> None:
        ip_count = self._peek(_derived_key("login_fail:ip", client_ip or "unknown"))
        acct_ip_count = self._peek(
            _derived_key("login_fail:acct_ip", _acct_ip_value(normalized_email, client_ip))
        )
        acct_count = self._peek(_derived_key("login_fail:acct", normalized_email))
        if (
            ip_count >= self.ip_max_attempts
            or acct_ip_count >= self.max_attempts
            or acct_count >= self.acct_global_max_attempts
        ):
            raise RateLimitExceededError()

    def record_login_failure(self, *, client_ip: str, normalized_email: str) -> None:
        self._hit(_derived_key("login_fail:ip", client_ip or "unknown"))
        self._hit(_derived_key("login_fail:acct_ip", _acct_ip_value(normalized_email, client_ip)))
        self._hit(_derived_key("login_fail:acct", normalized_email))

    def record_login_success(self, *, client_ip: str, normalized_email: str) -> None:
        self._clear(_derived_key("login_fail:acct_ip", _acct_ip_value(normalized_email, client_ip)))

    def check_rate_limit(
        self,
        *,
        scope: str,
        key_value: str,
        max_attempts: int,
        window_seconds: int,
    ) -> None:
        count = self._hit(_derived_key(scope, key_value), window_seconds=window_seconds)
        if count > max_attempts:
            raise RateLimitExceededError()

    def check_login_attempt(self, *, client_ip: str, normalized_email: str) -> None:
        self.check_login_allowed(client_ip=client_ip, normalized_email=normalized_email)
        self.record_login_failure(client_ip=client_ip, normalized_email=normalized_email)


class RedisLoginRateLimiter:
    """Atomic Redis rate limiter with separate failure tracking and scoped limits."""

    def __init__(
        self,
        redis_client: Redis,
        *,
        max_attempts: int = 5,
        window_seconds: int = 300,
        fail_closed: bool = False,
        ip_max_attempts: int | None = None,
    ) -> None:
        self.redis = redis_client
        self.max_attempts = max_attempts
        self.ip_max_attempts = ip_max_attempts if ip_max_attempts is not None else max_attempts
        self.acct_global_max_attempts = max(max_attempts * 4, self.ip_max_attempts)
        self.window_seconds = window_seconds
        self.fail_closed = fail_closed
        self._fallback = InMemoryRateLimiter(
            max_attempts=max_attempts,
            window_seconds=window_seconds,
            ip_max_attempts=self.ip_max_attempts,
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
            ip_max_attempts=current.auth_login_rate_limit_ip_max_attempts,
        )

    def _incr_key(self, key: str, *, window_seconds: int | None = None) -> int:
        ttl = window_seconds if window_seconds is not None else self.window_seconds
        result = self.redis.eval(_ATOMIC_INCR_EXPIRE_LUA, 1, key, str(ttl))
        return int(result)

    def _get_count(self, key: str) -> int:
        raw = self.redis.get(key)
        return int(raw) if raw is not None else 0

    def check_login_allowed(self, *, client_ip: str, normalized_email: str) -> None:
        ip_key = _derived_key("login_fail:ip", client_ip or "unknown")
        acct_ip_key = _derived_key(
            "login_fail:acct_ip", _acct_ip_value(normalized_email, client_ip)
        )
        acct_key = _derived_key("login_fail:acct", normalized_email)
        try:
            ip_count = self._get_count(ip_key)
            acct_ip_count = self._get_count(acct_ip_key)
            acct_count = self._get_count(acct_key)
        except RedisError as exc:
            if self.fail_closed:
                logger.error("Redis rate limiter unavailable in production")
                raise RateLimiterUnavailableError() from exc
            logger.warning("Redis rate limiter unavailable; using process-local fallback")
            self._fallback.check_login_allowed(
                client_ip=client_ip,
                normalized_email=normalized_email,
            )
            return

        if (
            ip_count >= self.ip_max_attempts
            or acct_ip_count >= self.max_attempts
            or acct_count >= self.acct_global_max_attempts
        ):
            raise RateLimitExceededError()

    def record_login_failure(self, *, client_ip: str, normalized_email: str) -> None:
        ip_key = _derived_key("login_fail:ip", client_ip or "unknown")
        acct_ip_key = _derived_key(
            "login_fail:acct_ip", _acct_ip_value(normalized_email, client_ip)
        )
        acct_key = _derived_key("login_fail:acct", normalized_email)
        try:
            self._incr_key(ip_key)
            self._incr_key(acct_ip_key)
            self._incr_key(acct_key)
        except RedisError as exc:
            if self.fail_closed:
                logger.error("Redis rate limiter unavailable in production")
                raise RateLimiterUnavailableError() from exc
            logger.warning("Redis rate limiter unavailable; using process-local fallback")
            self._fallback.record_login_failure(
                client_ip=client_ip,
                normalized_email=normalized_email,
            )

    def record_login_success(self, *, client_ip: str, normalized_email: str) -> None:
        acct_ip_key = _derived_key(
            "login_fail:acct_ip", _acct_ip_value(normalized_email, client_ip)
        )
        try:
            self.redis.delete(acct_ip_key)
        except RedisError as exc:
            if self.fail_closed:
                logger.error("Redis rate limiter unavailable in production")
                raise RateLimiterUnavailableError() from exc
            logger.warning("Redis rate limiter unavailable; using process-local fallback")
            self._fallback.record_login_success(
                client_ip=client_ip,
                normalized_email=normalized_email,
            )

    def check_rate_limit(
        self,
        *,
        scope: str,
        key_value: str,
        max_attempts: int,
        window_seconds: int,
    ) -> None:
        key = _derived_key(scope, key_value)
        try:
            count = self._incr_key(key, window_seconds=window_seconds)
        except RedisError as exc:
            if self.fail_closed:
                logger.error("Redis rate limiter unavailable in production")
                raise RateLimiterUnavailableError() from exc
            logger.warning("Redis rate limiter unavailable; using process-local fallback")
            self._fallback.check_rate_limit(
                scope=scope,
                key_value=key_value,
                max_attempts=max_attempts,
                window_seconds=window_seconds,
            )
            return

        if count > max_attempts:
            raise RateLimitExceededError()

    def check_login_attempt(self, *, client_ip: str, normalized_email: str) -> None:
        self.check_login_allowed(client_ip=client_ip, normalized_email=normalized_email)
        self.record_login_failure(client_ip=client_ip, normalized_email=normalized_email)
