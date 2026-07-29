"""Per-origin request limiting for the ingestion endpoint."""

from collections import defaultdict, deque
from threading import Lock
from time import monotonic
import os

from fastapi import Request


_STATE_LOCK = Lock()
_REQUESTS: dict[str, deque[float]] = defaultdict(deque)


def _limit_per_minute() -> int:
    return max(1, int(os.environ.get("RATE_LIMIT_PER_MINUTE", "60")))


def _window_seconds() -> int:
    return max(1, int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60")))


def _origin(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client is not None and request.client.host:
        return request.client.host
    return "unknown"


def check_request(request: Request) -> tuple[bool, dict[str, object]]:
    origin = _origin(request)
    now = monotonic()
    limit = _limit_per_minute()
    window = _window_seconds()

    with _STATE_LOCK:
        bucket = _REQUESTS[origin]
        while bucket and now - bucket[0] >= window:
            bucket.popleft()
        if len(bucket) >= limit:
            return False, {
                "origin": origin,
                "limit": limit,
                "window_seconds": window,
            }
        bucket.append(now)
        return True, {
            "origin": origin,
            "limit": limit,
            "window_seconds": window,
        }


def reset_state() -> None:
    with _STATE_LOCK:
        _REQUESTS.clear()