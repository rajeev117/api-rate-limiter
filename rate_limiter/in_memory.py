from __future__ import annotations

import math
import time
from collections import deque

from ._locks import KeyedLock
from .config import SlidingWindowConfig, TokenBucketConfig
from .results import RateLimitResult


class TokenBucketLimiter:
    def __init__(self, config: TokenBucketConfig) -> None:
        if config.capacity <= 0:
            raise ValueError("capacity must be > 0")
        if config.refill_rate < 0:
            raise ValueError("refill_rate must be >= 0")

        self._cfg = config
        self._locks = KeyedLock()
        # key -> (tokens, ts)
        self._state: dict[str, tuple[float, float]] = {}

    def check(self, key: str, tokens: int = 1) -> RateLimitResult:
        if tokens <= 0:
            raise ValueError("tokens must be > 0")

        now = time.monotonic()
        with self._locks.lock_for(key):
            stored = self._state.get(key)
            if stored is None:
                current_tokens = float(self._cfg.capacity)
                ts = now
            else:
                current_tokens, ts = stored

            delta = max(0.0, now - ts)
            refill = delta * float(self._cfg.refill_rate)
            if refill > 0:
                current_tokens = min(float(self._cfg.capacity), current_tokens + refill)
                ts = now

            allowed = current_tokens >= tokens
            retry_after_ms = 0
            if allowed:
                current_tokens -= float(tokens)
            else:
                missing = float(tokens) - current_tokens
                if self._cfg.refill_rate > 0:
                    retry_after_ms = int(math.ceil((missing / float(self._cfg.refill_rate)) * 1000.0))

            self._state[key] = (current_tokens, ts)

        return RateLimitResult(
            allowed=allowed,
            remaining=current_tokens,
            retry_after_ms=retry_after_ms,
            metadata={"algorithm": "token_bucket", "backend": "memory"},
        )

    def allow(self, key: str, tokens: int = 1) -> bool:
        return self.check(key, tokens=tokens).allowed


class SlidingWindowLimiter:
    def __init__(self, config: SlidingWindowConfig) -> None:
        if config.window_size_ms <= 0:
            raise ValueError("window_size_ms must be > 0")
        if config.max_requests <= 0:
            raise ValueError("max_requests must be > 0")

        self._cfg = config
        self._locks = KeyedLock()
        # key -> deque[timestamp_ms]
        self._state: dict[str, deque[int]] = {}

    def check(self, key: str) -> RateLimitResult:
        now_ms = time.monotonic_ns() // 1_000_000
        cutoff = now_ms - self._cfg.window_size_ms

        with self._locks.lock_for(key):
            q = self._state.get(key)
            if q is None:
                q = deque()
                self._state[key] = q

            while q and q[0] <= cutoff:
                q.popleft()

            if len(q) < self._cfg.max_requests:
                q.append(now_ms)
                remaining = float(self._cfg.max_requests - len(q))
                return RateLimitResult(
                    allowed=True,
                    remaining=remaining,
                    retry_after_ms=0,
                    metadata={
                        "algorithm": "sliding_window_log",
                        "backend": "memory",
                        "window_size_ms": self._cfg.window_size_ms,
                    },
                )

            oldest = q[0]
            retry_after_ms = max(0, int(self._cfg.window_size_ms - (now_ms - oldest)))
            return RateLimitResult(
                allowed=False,
                remaining=0.0,
                retry_after_ms=retry_after_ms,
                metadata={
                    "algorithm": "sliding_window_log",
                    "backend": "memory",
                    "window_size_ms": self._cfg.window_size_ms,
                },
            )

    def allow(self, key: str) -> bool:
        return self.check(key).allowed
