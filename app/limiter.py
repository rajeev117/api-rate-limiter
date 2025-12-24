from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import redis


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    tokens_left: float
    retry_after_ms: int


class RedisTokenBucket:
    def __init__(
        self,
        client: redis.Redis,
        *,
        key_prefix: str = "rl",
        capacity: int,
        refill_rate_per_sec: float,
    ) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be > 0")
        if refill_rate_per_sec < 0:
            raise ValueError("refill_rate_per_sec must be >= 0")

        self._redis = client
        self._key_prefix = key_prefix
        self._capacity = capacity
        self._refill_rate_per_ms = refill_rate_per_sec / 1000.0

        lua_path = Path(__file__).with_name("limiter.lua")
        self._script = lua_path.read_text(encoding="utf-8")
        self._sha: Optional[str] = None

    def _bucket_key(self, key: str) -> str:
        return f"{self._key_prefix}:{key}"

    def allow(self, *, key: str, tokens: int = 1) -> RateLimitResult:
        now_ms = int(time.time() * 1000)
        bucket_key = self._bucket_key(key)

        # Use EVALSHA for performance; fall back to EVAL on script cache miss.
        args = [now_ms, self._capacity, self._refill_rate_per_ms, tokens]
        try:
            if self._sha is None:
                self._sha = self._redis.script_load(self._script)
            allowed, tokens_left, retry_after_ms = self._redis.evalsha(
                self._sha, 1, bucket_key, *args
            )
        except redis.exceptions.NoScriptError:
            allowed, tokens_left, retry_after_ms = self._redis.eval(self._script, 1, bucket_key, *args)
            # Re-load to restore fast path.
            self._sha = self._redis.script_load(self._script)

        return RateLimitResult(
            allowed=bool(int(allowed)),
            tokens_left=float(tokens_left),
            retry_after_ms=int(retry_after_ms),
        )


def retry_after_header_value(retry_after_ms: int) -> Optional[str]:
    if retry_after_ms <= 0:
        return None
    # HTTP Retry-After supports seconds; round up.
    seconds = (retry_after_ms + 999) // 1000
    return str(max(1, seconds))


def client_ip_from_headers(
    x_forwarded_for: Optional[str],
    x_real_ip: Optional[str],
    fallback: str,
) -> str:
    if x_real_ip:
        return x_real_ip.strip()
    if x_forwarded_for:
        # left-most is original client
        return x_forwarded_for.split(",")[0].strip()
    return fallback


def is_redis_available(err: BaseException) -> Tuple[bool, str]:
    # Keep this simple; callers decide fail-open/closed.
    return isinstance(err, (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError)), str(err)
