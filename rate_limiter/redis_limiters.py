from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import redis

from .config import RedisConfig, SlidingWindowConfig, TokenBucketConfig
from .results import RateLimitResult


@dataclass(frozen=True)
class _LuaScript:
    source: str
    sha: Optional[str] = None


def _load_script_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class RedisTokenBucketLimiter:
    def __init__(
        self,
        config: TokenBucketConfig,
        redis_config: RedisConfig,
        client: redis.Redis | None = None,
    ) -> None:
        if config.capacity <= 0:
            raise ValueError("capacity must be > 0")
        if config.refill_rate < 0:
            raise ValueError("refill_rate must be >= 0")

        self._cfg = config
        self._redis_cfg = redis_config
        self._redis = client or redis.Redis.from_url(
            redis_config.redis_url(),
            decode_responses=True,
            socket_connect_timeout=redis_config.socket_connect_timeout_s,
            socket_timeout=redis_config.socket_timeout_s,
            retry_on_timeout=True,
        )

        lua_path = Path(__file__).with_name("lua") / "token_bucket.lua"
        self._script = _LuaScript(source=_load_script_text(lua_path))

    def _key(self, key: str) -> str:
        return f"{self._redis_cfg.key_prefix}{key}"

    def check(self, key: str, tokens: int = 1) -> RateLimitResult:
        if tokens <= 0:
            raise ValueError("tokens must be > 0")

        now_ms = int(time.time() * 1000)
        bucket_key = self._key(key)
        args = [now_ms, self._cfg.capacity, self._cfg.refill_rate / 1000.0, tokens]

        try:
            if self._script.sha is None:
                object.__setattr__(self._script, "sha", self._redis.script_load(self._script.source))
            allowed, tokens_left, retry_after_ms = self._redis.evalsha(
                self._script.sha, 1, bucket_key, *args
            )
        except redis.exceptions.NoScriptError:
            allowed, tokens_left, retry_after_ms = self._redis.eval(
                self._script.source, 1, bucket_key, *args
            )
            object.__setattr__(self._script, "sha", self._redis.script_load(self._script.source))
        except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as exc:
            if self._redis_cfg.fail_open:
                return RateLimitResult(
                    allowed=True,
                    remaining=float("inf"),
                    retry_after_ms=0,
                    metadata={
                        "algorithm": "token_bucket",
                        "backend": "redis",
                        "mode": "fail_open",
                        "error": str(exc),
                    },
                )
            return RateLimitResult(
                allowed=False,
                remaining=0.0,
                retry_after_ms=0,
                metadata={
                    "algorithm": "token_bucket",
                    "backend": "redis",
                    "mode": "fail_closed",
                    "error": str(exc),
                },
            )

        return RateLimitResult(
            allowed=bool(int(allowed)),
            remaining=float(tokens_left),
            retry_after_ms=int(retry_after_ms),
            metadata={"algorithm": "token_bucket", "backend": "redis"},
        )

    def allow(self, key: str, tokens: int = 1) -> bool:
        return self.check(key, tokens=tokens).allowed


class RedisSlidingWindowLimiter:
    def __init__(
        self,
        config: SlidingWindowConfig,
        redis_config: RedisConfig,
        client: redis.Redis | None = None,
    ) -> None:
        if config.window_size_ms <= 0:
            raise ValueError("window_size_ms must be > 0")
        if config.max_requests <= 0:
            raise ValueError("max_requests must be > 0")

        self._cfg = config
        self._redis_cfg = redis_config
        self._redis = client or redis.Redis.from_url(
            redis_config.redis_url(),
            decode_responses=True,
            socket_connect_timeout=redis_config.socket_connect_timeout_s,
            socket_timeout=redis_config.socket_timeout_s,
            retry_on_timeout=True,
        )

        lua_path = Path(__file__).with_name("lua") / "sliding_window.lua"
        self._script = _LuaScript(source=_load_script_text(lua_path))

    def _key(self, key: str) -> str:
        return f"{self._redis_cfg.key_prefix}{key}"

    def check(self, key: str) -> RateLimitResult:
        now_ms = int(time.time() * 1000)
        zset_key = self._key(key)
        args = [now_ms, self._cfg.window_size_ms, self._cfg.max_requests]

        try:
            if self._script.sha is None:
                object.__setattr__(self._script, "sha", self._redis.script_load(self._script.source))
            allowed, remaining, retry_after_ms = self._redis.evalsha(
                self._script.sha, 1, zset_key, *args
            )
        except redis.exceptions.NoScriptError:
            allowed, remaining, retry_after_ms = self._redis.eval(
                self._script.source, 1, zset_key, *args
            )
            object.__setattr__(self._script, "sha", self._redis.script_load(self._script.source))
        except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as exc:
            if self._redis_cfg.fail_open:
                return RateLimitResult(
                    allowed=True,
                    remaining=float("inf"),
                    retry_after_ms=0,
                    metadata={
                        "algorithm": "sliding_window_log",
                        "backend": "redis",
                        "mode": "fail_open",
                        "error": str(exc),
                    },
                )
            return RateLimitResult(
                allowed=False,
                remaining=0.0,
                retry_after_ms=0,
                metadata={
                    "algorithm": "sliding_window_log",
                    "backend": "redis",
                    "mode": "fail_closed",
                    "error": str(exc),
                },
            )

        return RateLimitResult(
            allowed=bool(int(allowed)),
            remaining=float(remaining),
            retry_after_ms=int(retry_after_ms),
            metadata={"algorithm": "sliding_window_log", "backend": "redis"},
        )

    def allow(self, key: str) -> bool:
        return self.check(key).allowed
