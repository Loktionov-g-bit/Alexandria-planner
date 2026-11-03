"""Per-IP throttling of failed sign-ins (passwords and 2FA codes).

Per-account locking already stops guessing one account; this stops one address from walking through many
accounts (password spraying). In memory: it resets on restart, which is fine for slowing attackers down.
The IP is the one uvicorn resolved, so behind a reverse proxy set PLANNER_FORWARDED_ALLOW_IPS to the proxy's address.
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException

from .config import get_settings

_fails: dict[str, deque[float]] = defaultdict(deque)
MAX_TRACKED = 50_000  # a flood of fake addresses must not eat the memory


def _recent(ip: str, now: float) -> deque[float]:
    window = get_settings().ip_window_minutes * 60
    q = _fails[ip]
    while q and q[0] < now - window:
        q.popleft()
    return q


def check(ip: str | None) -> None:
    """Raise 429 while this IP is over the limit."""
    if not ip:
        return
    if len(_recent(ip, time.monotonic())) >= get_settings().ip_max_failures:
        raise HTTPException(429, "auth.too_many_attempts")


def failed(ip: str | None) -> None:
    if not ip:
        return
    if len(_fails) > MAX_TRACKED:
        _fails.clear()
    _recent(ip, time.monotonic()).append(time.monotonic())


def reset() -> None:
    _fails.clear()
