from __future__ import annotations

import time

from rate_limiter import SlidingWindowConfig, SlidingWindowLimiter


def test_sliding_window_throttles_when_limit_reached() -> None:
    limiter = SlidingWindowLimiter(SlidingWindowConfig(window_size_ms=200, max_requests=2))
    key = "k"

    assert limiter.allow(key) is True
    assert limiter.allow(key) is True
    r = limiter.check(key)
    assert r.allowed is False
    assert r.retry_after_ms >= 0


def test_sliding_window_allows_after_window_passes() -> None:
    limiter = SlidingWindowLimiter(SlidingWindowConfig(window_size_ms=150, max_requests=1))
    key = "k"

    assert limiter.allow(key) is True
    assert limiter.allow(key) is False

    time.sleep(0.18)
    assert limiter.allow(key) is True
