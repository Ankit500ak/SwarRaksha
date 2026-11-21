"""Simple in-memory sliding-window rate limiter (per IP, per bucket).

Single-process by design for the current deployment shape; swap the
store for Redis before scaling to multiple API workers (PLAN.md §5
already places stream/session state in Redis).
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, bucket: str, key: str, limit: int,
              window_s: float = 60.0) -> bool:
        if limit <= 0:
            return True
        now = time.monotonic()
        with self._lock:
            q = self._hits[(bucket, key)]
            while q and q[0] <= now - window_s:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()
