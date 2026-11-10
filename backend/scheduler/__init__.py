"""CoursePilot's scheduling engine.

This package must stay pure: no web framework, no ORM, no ``app``, no clock and no randomness.
``tests/unit/test_architecture.py`` enforces that. See docs/SCHEDULING_ENGINE.md.
"""

from scheduler.planner import plan

__all__ = ["plan"]
