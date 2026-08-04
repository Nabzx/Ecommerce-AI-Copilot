"""
A small rate limiter for the endpoints that cost money or CPU.

Sliding window, kept in memory. That's fine for one instance running one
store — if StoreSense ever ran on several machines this would need to move to
Redis, but adding Redis now would be solving a problem nobody has.
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.config import settings


class RateLimiter:
    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window = window_seconds
        # caller -> timestamps of their recent requests
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, caller: str) -> None:
        """Record a request, or raise 429 if the caller has had too many."""
        now = time.monotonic()
        hits = self._hits[caller]

        # Drop anything that has fallen out of the back of the window.
        while hits and now - hits[0] > self.window:
            hits.popleft()

        if len(hits) >= self.limit:
            retry_after = int(self.window - (now - hits[0])) + 1
            raise HTTPException(
                status_code=429,
                detail=f"Too many requests. Try again in {retry_after}s.",
                headers={"Retry-After": str(retry_after)},
            )

        hits.append(now)


_limiter = RateLimiter(settings.rate_limit_requests, settings.rate_limit_window_seconds)


def rate_limit(request: Request) -> None:
    """FastAPI dependency — add to any route that hits the model."""
    caller = request.client.host if request.client else "unknown"
    _limiter.check(caller)
