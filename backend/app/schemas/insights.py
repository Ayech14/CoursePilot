"""Dashboard and analytics contracts. Every figure is computed from the student's own records."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from app.models.enums import TaskType
from app.schemas.schedule import SessionRead


class DeadlineItem(BaseModel):
    task_id: uuid.UUID
    title: str
    task_type: TaskType
    deadline_at: datetime
    course_name: str | None
    course_color: str | None
    remaining_minutes: int


class AttentionItem(BaseModel):
    task_id: uuid.UUID
    title: str
    course_color: str | None
    deadline_at: datetime
    reason: Literal["overdue", "not_fully_planned", "due_soon"]
    unplanned_minutes: int


class WeekSummary(BaseModel):
    week_start: date
    studied_minutes: int
    planned_minutes: int


class TaskCounts(BaseModel):
    completed: int
    remaining: int
    overdue: int


class CourseWorkload(BaseModel):
    course_id: uuid.UUID | None
    name: str
    code: str | None
    color: str | None
    open_tasks: int
    completed_tasks: int
    remaining_minutes: int


class TodayProgress(BaseModel):
    studied_minutes: int
    goal_minutes: int | None
    streak_days: int
    """Consecutive days with timed study, ending today or, if nothing is timed yet, yesterday."""
    studied_today: bool


class RecentSession(BaseModel):
    session_id: uuid.UUID
    task_id: uuid.UUID
    task_title: str
    course_name: str | None
    course_color: str | None
    ended_at: datetime
    minutes: int


class DashboardRead(BaseModel):
    today: list[SessionRead]
    upcoming_assignments: list[DeadlineItem]
    upcoming_exams: list[DeadlineItem]
    attention: list[AttentionItem]
    attention_total: int
    week: WeekSummary
    tasks: TaskCounts
    workload: list[CourseWorkload]
    progress: TodayProgress
    recent: list[RecentSession]


class WeekMinutes(BaseModel):
    week_start: date
    minutes: int


class WeekCount(BaseModel):
    week_start: date
    count: int


class CourseMinutes(BaseModel):
    course_id: uuid.UUID | None
    name: str
    color: str | None
    minutes: int


class EstimateComparison(BaseModel):
    task_id: uuid.UUID
    title: str
    estimated_minutes: int
    actual_minutes: int


class EstimateSummary(BaseModel):
    tasks_compared: int
    estimated_minutes: int
    actual_minutes: int
    recent: list[EstimateComparison]


class UpcomingDay(BaseModel):
    date: date
    planned_minutes: int
    deadlines: int


class ConsistencyDay(BaseModel):
    date: date
    minutes: int


class Consistency(BaseModel):
    days: list[ConsistencyDay]
    active_days: int
    current_streak: int
    sessions_completed: int
    sessions_missed: int


class AnalyticsRead(BaseModel):
    weekly_minutes: list[WeekMinutes]
    minutes_per_course: list[CourseMinutes]
    completions: list[WeekCount]
    workload: list[CourseWorkload]
    estimates: EstimateSummary
    upcoming: list[UpcomingDay]
    consistency: Consistency


class DayTask(BaseModel):
    task_id: uuid.UUID
    title: str
    course_color: str | None
    minutes: int


class DayItem(BaseModel):
    task_id: uuid.UUID
    title: str
    course_color: str | None


class DayDeadline(BaseModel):
    task_id: uuid.UUID
    title: str
    task_type: TaskType
    deadline_at: datetime
    course_color: str | None
    completed: bool


class MonthDay(BaseModel):
    date: date
    studied_minutes: int
    studied: list[DayTask]
    completed: list[DayItem]
    deadlines: list[DayDeadline]


class MonthRead(BaseModel):
    month: date
    goal_minutes: int | None
    days: list[MonthDay]
