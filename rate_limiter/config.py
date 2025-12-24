from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TokenBucketConfig:
    capacity: int
    refill_rate: float  # tokens per second


@dataclass(frozen=True)
class SlidingWindowConfig:
    window_size_ms: int
    max_requests: int


@dataclass(frozen=True)
class RedisConfig:
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    key_prefix: str = "rate:"

    # When Redis is unavailable, allow requests through.
    fail_open: bool = True

    socket_connect_timeout_s: float = 1.0
    socket_timeout_s: float = 1.0

    def redis_url(self) -> str:
        return f"redis://{self.host}:{self.port}/{self.db}"
