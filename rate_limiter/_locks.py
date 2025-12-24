from __future__ import annotations

import threading


class KeyedLock:
    """Per-key mutex.

    This keeps a map of key -> Lock to reduce contention vs a single global lock.
    For simplicity it doesn't garbage-collect old locks.
    """

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}

    def lock_for(self, key: str) -> threading.Lock:
        with self._guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._locks[key] = lock
            return lock
