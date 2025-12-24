from __future__ import annotations

import time

from rate_limiter import TokenBucketConfig, TokenBucketLimiter


def test_token_bucket_allows_burst_then_throttles() -> None:
    limiter = TokenBucketLimiter(TokenBucketConfig(capacity=3, refill_rate=0))
    key = "k"

    assert limiter.allow(key) is True
    assert limiter.allow(key) is True
    assert limiter.allow(key) is True
    assert limiter.allow(key) is False


def test_token_bucket_refills_over_time() -> None:
    limiter = TokenBucketLimiter(TokenBucketConfig(capacity=1, refill_rate=10))
    key = "k"

    assert limiter.allow(key) is True
    assert limiter.allow(key) is False

    time.sleep(0.12)
    assert limiter.allow(key) is True
