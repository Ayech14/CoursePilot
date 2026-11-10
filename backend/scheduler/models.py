"""Plain data going into and out of the engine. IDs are opaque strings."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


@dataclass(frozen=True)
class Interval:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class WeeklyTime:
    """Local wall-clock time. Monday is 0; minutes run from local midnight up to 1440."""

    day_of_week: int
    start_minute: int
    end_minute: int


@dataclass(frozen=True)
class Preferences:
    preferred_session_minutes: int
    min_session_minutes: int
    break_minutes: int
    max_daily_minutes: int
    deadline_buffer_hours: int


@dataclass(frozen=True)
class TaskInput:
    id: str
    remaining_minutes: int
    priority: int  # 1 (low) to 4 (critical).
    deadline: datetime | None = None
    course_id: str | None = None


class SessionClass(StrEnum):
    LOCKED = "locked"  # Never moved or removed.
    STICKY = "sticky"  # The student changed it; kept unless impossible.
    FLEXIBLE = "flexible"  # The engine's own work; free to replace.


@dataclass(frozen=True)
class ExistingSession:
    id: str
    task_id: str
    start: datetime
    end: datetime
    session_class: SessionClass


@dataclass(frozen=True)
class PlanRequest:
    now: datetime
    timezone: str  # IANA name.
    horizon_end: datetime
    tasks: tuple[TaskInput, ...]
    windows: tuple[WeeklyTime, ...]
    preferences: Preferences
    weekly_blocks: tuple[WeeklyTime, ...] = ()
    one_off_blocks: tuple[Interval, ...] = ()
    existing_sessions: tuple[ExistingSession, ...] = ()
    # Finished work today. Unlike a session still on the schedule, it has no slot to count.
    studied_today_minutes: int = 0


class Reason(StrEnum):
    DEADLINE_PRESSURE = "deadline_pressure"
    HIGH_PRIORITY = "high_priority"
    COURSE_BALANCE = "course_balance"
    VARIETY = "variety"
    DEADLINE_GUARD = "deadline_guard"
    BEST_EFFORT = "best_effort"


@dataclass(frozen=True)
class Explanation:
    primary_reason: Reason
    factors: dict[str, float]
    guard_override: bool
    deadline: datetime | None


@dataclass(frozen=True)
class Placement:
    task_id: str
    start: datetime
    end: datetime
    explanation: Explanation

    @property
    def minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


class RiskReason(StrEnum):
    OVERDUE = "overdue"  # The deadline has already passed.
    INSUFFICIENT_TIME = "insufficient_time"


@dataclass(frozen=True)
class AtRiskTask:
    task_id: str
    shortfall_minutes: int
    reason: RiskReason


@dataclass(frozen=True)
class UnplacedTask:
    """Work with no deadline inside the horizon that was simply not reached. Not a problem."""

    task_id: str
    minutes: int


@dataclass(frozen=True)
class PlanResult:
    placements: tuple[Placement, ...]
    at_risk: tuple[AtRiskTask, ...] = ()
    unplaced: tuple[UnplacedTask, ...] = field(default=())


class ChangeKind(StrEnum):
    CREATE = "create"
    MOVE = "move"
    RESIZE = "resize"
    REMOVE = "remove"


class RepairReason(StrEnum):
    TASK_FINISHED = "task_finished"
    LESS_WORK_NEEDED = "less_work_needed"
    PAST_DEADLINE = "past_deadline"
    OUTSIDE_AVAILABILITY = "outside_availability"
    TIME_BLOCKED = "time_blocked"
    DAILY_LIMIT = "daily_limit"
    SCHEDULE_RULES = "schedule_rules"
    MAKING_ROOM = "making_room"
    REBUILT = "rebuilt"


@dataclass(frozen=True)
class SessionChange:
    kind: ChangeKind
    task_id: str
    session_id: str | None = None
    before: Interval | None = None
    after: Interval | None = None
    reason: RepairReason | None = None
    explanation: Explanation | None = None
    sticky_released: bool = False  # The student's own edit is being overridden.


@dataclass(frozen=True)
class RepairResult:
    changes: tuple[SessionChange, ...]
    unchanged: int
    at_risk: tuple[AtRiskTask, ...] = ()
    unplaced: tuple[UnplacedTask, ...] = ()
