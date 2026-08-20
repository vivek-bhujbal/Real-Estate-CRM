import asyncio
import time
from collections import deque
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request
from redis.asyncio import Redis

from app.core.errors import AppError


def rate_limit(
    *, requests: int, window_seconds: int
) -> Callable[[Request], Coroutine[Any, Any, None]]:
    fallback_attempts: dict[str, deque[float]] = {}
    fallback_lock = asyncio.Lock()

    async def enforce_fallback(key: str) -> None:
        now = time.monotonic()
        cutoff = now - window_seconds
        async with fallback_lock:
            attempts = fallback_attempts.setdefault(key, deque())
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if len(attempts) >= requests:
                raise _rate_limited_error()
            attempts.append(now)
            if len(fallback_attempts) > 10_000:
                oldest_key = next(iter(fallback_attempts))
                if oldest_key != key:
                    fallback_attempts.pop(oldest_key, None)

    async def dependency(request: Request) -> None:
        redis: Redis | None = getattr(request.app.state, "redis", None)
        identity = request.client.host if request.client else "unknown"
        key = f"rate:{request.url.path}:{identity}"
        if redis is None:
            await enforce_fallback(key)
            return
        try:
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, window_seconds)
        except Exception:
            await enforce_fallback(key)
            return
        if count > requests:
            raise _rate_limited_error()

    return dependency


def _rate_limited_error() -> AppError:
    return AppError(
        status_code=429,
        code="RATE_LIMITED",
        message="Too many requests; please try again later",
        headers={"Retry-After": "60"},
    )
