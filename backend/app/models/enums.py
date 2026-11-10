"""Domain enumerations. Values are stored as strings; see ARCHITECTURE.md section 3.6."""

from enum import IntEnum, StrEnum


class TaskType(StrEnum):
    ASSIGNMENT = "assignment"
    PROJECT = "project"
    MIDTERM = "midterm"
    FINAL_EXAM = "final_exam"
    QUIZ = "quiz"
    READING = "reading"
    REVISION = "revision"
    STUDY = "study"


class TaskStatus(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class Priority(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class SessionStatus(StrEnum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETED = "completed"
    MISSED = "missed"
    CANCELLED = "cancelled"


class SessionOrigin(StrEnum):
    AUTO = "auto"
    MANUAL = "manual"


class ProposalStatus(StrEnum):
    PENDING = "pending"
    APPLIED = "applied"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class ProposalTrigger(StrEnum):
    GENERATE = "generate"
    REGENERATE = "regenerate"
    SESSION_MISSED = "session_missed"
    TASK_CHANGED = "task_changed"
    AVAILABILITY_CHANGED = "availability_changed"
    MANUAL_REQUEST = "manual_request"


class ChangeAction(StrEnum):
    CREATE = "create"
    MOVE = "move"
    RESIZE = "resize"
    REMOVE = "remove"


class NotificationKind(StrEnum):
    DEADLINE_APPROACHING = "deadline_approaching"
    TASK_OVERDUE = "task_overdue"
    TASK_UNFINISHED = "task_unfinished"
    SCHEDULE_ADJUSTED = "schedule_adjusted"
    WORKLOAD_CONFLICT = "workload_conflict"
