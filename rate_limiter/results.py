from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: float
    retry_after_ms: int
    metadata: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "remaining": self.remaining,
            "retry_after_ms": self.retry_after_ms,
            "metadata": dict(self.metadata),
        }


def retry_after_header_value(retry_after_ms: int) -> Optional[str]:
    if retry_after_ms <= 0:
        return None
    # HTTP Retry-After supports seconds; round up.
    seconds = (retry_after_ms + 999) // 1000
    return str(max(1, seconds))
