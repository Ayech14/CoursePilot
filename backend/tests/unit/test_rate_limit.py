"""The sliding window behind sign-in limits, on a clock the test controls."""

import pytest

from app.core.errors import RateLimitedError
from app.core.rate_limit import SlidingWindow


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_allows_up_to_the_limit_then_says_how_long_to_wait() -> None:
    clock = Clock()
    window = SlidingWindow(3, 60, clock)
    for _ in range(3):
        window.check("k")
        window.record("k")
        clock.now += 10
    with pytest.raises(RateLimitedError) as raised:
        window.check("k")
    # The first attempt was 30 seconds ago, so it falls out of the window in 30 more.
    assert raised.value.headers == {"Retry-After": "30"}
    assert raised.value.details == {"retry_after_seconds": 30}


def test_old_attempts_slide_out_of_the_window() -> None:
    clock = Clock()
    window = SlidingWindow(2, 60, clock)
    window.record("k")
    clock.now += 30
    window.record("k")
    clock.now += 31
    window.check("k")  # The first attempt is now over a minute old.


def test_keys_are_counted_separately_and_can_be_cleared() -> None:
    clock = Clock()
    window = SlidingWindow(1, 60, clock)
    window.record("a")
    window.check("b")
    with pytest.raises(RateLimitedError):
        window.check("a")
    window.clear("a")
    window.check("a")


def test_expired_keys_are_forgotten() -> None:
    clock = Clock()
    window = SlidingWindow(1, 60, clock)
    window.record("a")
    clock.now += 61
    window.check("a")
    assert window._events == {}
