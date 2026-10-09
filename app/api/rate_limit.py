"""
Per-user rate limiting for LLM-backed endpoints.

In-memory sliding window, per process: good enough for a single API instance. With several
workers/instances each one enforces the limit separately; move to Redis if that matters.
"""

import math
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Hashable, Optional

from fastapi import Depends, HTTPException, status

from app.api.deps import get_current_user
from app.config import settings
from app.models import User

WINDOW_SECONDS = 60.0


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._hits: Dict[Hashable, Deque[float]] = defaultdict(deque)

    def hit(self, key: Hashable, limit: int, window: float = WINDOW_SECONDS, now: Optional[float] = None) -> Optional[float]:
        """Record a request. Returns None if allowed, else seconds until a slot frees up."""
        now = time.monotonic() if now is None else now
        hits = self._hits[key]
        while hits and hits[0] <= now - window:
            hits.popleft()
        if len(hits) >= limit:
            return max(0.0, hits[0] + window - now)
        hits.append(now)
        return None

    def reset(self) -> None:
        self._hits.clear()


llm_limiter = SlidingWindowLimiter()


async def llm_rate_limit(current_user: User = Depends(get_current_user)) -> None:
    """Dependency: 429 when the user exceeds LLM_RATE_LIMIT_PER_MINUTE on LLM-backed endpoints."""
    limit = settings.LLM_RATE_LIMIT_PER_MINUTE
    if limit <= 0:
        return
    retry_after = llm_limiter.hit(current_user.id, limit)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many AI requests. Please wait a moment and try again.",
            headers={"Retry-After": str(max(1, math.ceil(retry_after)))},
        )
