import time
from typing import Dict, List
from fastapi import HTTPException, status
from app.config import settings

_user_request_timestamps: Dict[str, List[float]] = {}


def check_rate_limit(identifier: str, max_requests: int = None, window_seconds: int = 60) -> None:
   
    if max_requests is None:
        max_requests = settings.RATE_LIMIT_QUESTIONS_PER_MINUTE

    now = time.time()
    cutoff = now - window_seconds

    timestamps = _user_request_timestamps.get(identifier, [])
    timestamps = [t for t in timestamps if t > cutoff]

    if len(timestamps) >= max_requests:
        retry_after = int(window_seconds - (now - timestamps[0])) + 1
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: Maximum {max_requests} questions per {window_seconds}s. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)}
        )

    timestamps.append(now)
    _user_request_timestamps[identifier] = timestamps


def reset_rate_limits():
    _user_request_timestamps.clear()
