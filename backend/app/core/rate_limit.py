"""Limits on sign-in and registration attempts, to slow down password guessing.

Kept in memory, which is right for one server process: no Redis or other paid service is needed.
With several processes each keeps its own count, so the real limit is that many times higher;
moving the buckets to PostgreSQL would fix that if CoursePilot ever runs more than one.
"""

import math
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

from app.core.errors import RateLimitedError


@dataclass
class SlidingWindow:
    """At most `limit` events per key in any `window_seconds`."""

    limit: int
    window_seconds: float
    clock: Callable[[], float] = time.monotonic
    _events: dict[str, deque[float]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _trim(self, key: str, now: float) -> deque[float]:
        events = self._events.get(key, deque())
        while events and events[0] <= now - self.window_seconds:
            events.popleft()
        if events:
            self._events[key] = events
        else:
            self._events.pop(key, None)
        return events

    def check(self, key: str) -> None:
        """Raise if the key has used up its allowance. Records nothing."""
        with self._lock:
            now = self.clock()
            events = self._trim(key, now)
            if len(events) >= self.limit:
                wait = events[0] + self.window_seconds - now
                raise RateLimitedError(max(math.ceil(wait), 1))

    def record(self, key: str) -> None:
        with self._lock:
            now = self.clock()
            self._trim(key, now)
            self._events.setdefault(key, deque()).append(now)
            if len(self._events) > 10_000:
                # Forget keys whose events have all expired, so memory stays bounded.
                for stale in [
                    k for k, v in self._events.items() if v[-1] <= now - self.window_seconds
                ]:
                    del self._events[stale]

    def clear(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)


@dataclass
class AuthLimits:
    """The limits the authentication endpoints use. One set per running app."""

    # Failed sign-ins for one email from one address, and from one address across all emails.
    login_per_account: SlidingWindow = field(default_factory=lambda: SlidingWindow(5, 15 * 60))
    login_per_address: SlidingWindow = field(default_factory=lambda: SlidingWindow(20, 15 * 60))
    register_per_address: SlidingWindow = field(default_factory=lambda: SlidingWindow(10, 60 * 60))
