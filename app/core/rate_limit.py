"""In-memory sliding-window rate limiter.

$0-stack default (see DESIGN.md sect 10). This is a single-process limiter -
fine for the capstone's local/dev scope. Swap `_buckets` for a Redis
sorted-set implementation behind the same `enforce()` signature for a
multi-process deployment; no route code would need to change.
"""
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import HTTPException


@dataclass
class RateLimitRule:
    max_requests: int
    window_seconds: int


# Definition of Done requires per-IP AND per-widget limiting.
IP_RULE = RateLimitRule(max_requests=10, window_seconds=60)
WIDGET_RULE = RateLimitRule(max_requests=60, window_seconds=60)

_buckets: dict[str, deque] = defaultdict(deque)


def _check(key: str, rule: RateLimitRule) -> tuple[bool, int]:
    now = time.monotonic()
    bucket = _buckets[key]
    while bucket and now - bucket[0] > rule.window_seconds:
        bucket.popleft()
    if len(bucket) >= rule.max_requests:
        retry_after = int(rule.window_seconds - (now - bucket[0])) + 1
        return False, retry_after
    bucket.append(now)
    return True, 0


def enforce(ip: str, widget_id: str) -> None:
    """Raises 429 if either the IP or the widget is over its rate limit.
    A burst against one widget must not degrade service for a different
    widget or a different visitor - hence two independent keys."""
    ok, retry_after = _check(f"ip:{ip}", IP_RULE)
    if not ok:
        raise HTTPException(
            status_code=429,
            detail={"error": "rate_limited", "scope": "ip", "retry_after": retry_after},
        )

    ok, retry_after = _check(f"widget:{widget_id}", WIDGET_RULE)
    if not ok:
        raise HTTPException(
            status_code=429,
            detail={"error": "rate_limited", "scope": "widget", "retry_after": retry_after},
        )


def reset_all() -> None:
    """Test helper - clears all buckets between test cases."""
    _buckets.clear()
