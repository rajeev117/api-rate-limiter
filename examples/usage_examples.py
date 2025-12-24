from __future__ import annotations

import time

from rate_limiter import (
    RedisConfig,
    RedisSlidingWindowLimiter,
    RedisTokenBucketLimiter,
    SlidingWindowConfig,
    SlidingWindowLimiter,
    TokenBucketConfig,
    TokenBucketLimiter,
)


def in_memory_token_bucket() -> None:
    print("== In-memory token bucket ==")
    limiter = TokenBucketLimiter(TokenBucketConfig(capacity=5, refill_rate=2))
    key = "user-123"

    for i in range(8):
        r = limiter.check(key)
        print(i, r.allowed, f"remaining={r.remaining:.2f}")
        time.sleep(0.1)


def in_memory_sliding_window() -> None:
    print("== In-memory sliding window ==")
    limiter = SlidingWindowLimiter(SlidingWindowConfig(window_size_ms=1000, max_requests=5))
    key = "user-123"

    for i in range(8):
        r = limiter.check(key)
        print(i, r.allowed, f"retry_after_ms={r.retry_after_ms}")
        time.sleep(0.1)


def redis_token_bucket() -> None:
    print("== Redis token bucket ==")
    limiter = RedisTokenBucketLimiter(
        TokenBucketConfig(capacity=10, refill_rate=5),
        RedisConfig(host="localhost", port=6379, key_prefix="rate:api:", fail_open=True),
    )

    for i in range(15):
        r = limiter.check("user-123")
        print(i, r.allowed, f"remaining={r.remaining:.2f}")


def redis_sliding_window() -> None:
    print("== Redis sliding window ==")
    limiter = RedisSlidingWindowLimiter(
        SlidingWindowConfig(window_size_ms=1000, max_requests=5),
        RedisConfig(host="localhost", port=6379, key_prefix="rate:window:", fail_open=True),
    )

    for i in range(8):
        r = limiter.check("user-123")
        print(i, r.allowed, f"retry_after_ms={r.retry_after_ms}")


if __name__ == "__main__":
    in_memory_token_bucket()
    in_memory_sliding_window()
    # Uncomment if Redis is running locally
    # redis_token_bucket()
    # redis_sliding_window()
