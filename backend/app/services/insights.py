"""Read-only summaries for the dashboard and analytics pages.

Days and weeks are the student's local ones, and weeks start on Monday. Timed work is split at
local midnight, so a session that runs past midnight counts toward both days correctly.
"""

import uuid
from collections import defaultdict
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Course, StudyPreferences, StudySession, Task, User, WorkInterval
from app.models.enums import SessionStatus, TaskStatus
from app.schemas.insights import (
    AnalyticsRead,
    AttentionItem,
    Consistency,
    ConsistencyDay,
    CourseMinutes,
    CourseWorkload,
    DashboardRead,
    DayDeadline,
    DayItem,
    DayTask,
    DeadlineItem,
    EstimateComparison,
    EstimateSummary,
    MonthDay,
    MonthRead,
    RecentSession,
    TaskCounts,
    TodayProgress,
    UpcomingDay,
    WeekCount,
    WeekMinutes,
    WeekSummary,
)
from app.services.scheduling import (
    ACTIVE_STATUSES,
    list_sessions,
    local_day_bounds,
    reconcile_missed_sessions,
    rounded_minutes,
    worked_minutes,
)
from app.services.tasks import EXAM_TYPES
from scheduler.timeline import local_to_utc

_UPCOMING_LIMIT = 5
_ATTENTION_LIMIT = 8
_ATTENTION_WINDOW = timedelta(days=14)
_DUE_SOON = timedelta(hours=48)
_UPCOMING_DAYS = 14
_CONSISTENCY_DAYS = 28
_RECENT_ESTIMATES = 10
_RECENT_SESSIONS = 5
# How far back a streak is counted. A longer streak is reported as this many days.
_STREAK_LIMIT_DAYS = 366
_NO_COURSE = "No course"

_Row = tuple[Task, Course | None]


def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _start_of(day: date, zone: ZoneInfo) -> datetime:
    return local_to_utc(day, 0, zone)


def _seconds_by_day(start: datetime, end: datetime, zone: ZoneInfo) -> Iterable[tuple[date, float]]:
    """Split a stretch of time at each local midnight."""
    cursor = start
    while cursor < end:
        day = cursor.astimezone(zone).date()
        boundary = min(_start_of(day + timedelta(days=1), zone), end)
        yield day, (boundary - cursor).total_seconds()
        cursor = boundary


def _tasks(db: Session, user: User) -> list[_Row]:
    """Tasks that count. An archived course's tasks are out of the plan and out of these figures."""
    return [
        (task, course)
        for task, course in db.execute(
            select(Task, Course)
            .outerjoin(Course, Task.course_id == Course.id)
            .where(
                Task.user_id == user.id,
                or_(Task.course_id.is_(None), Course.archived_at.is_(None)),
            )
            .order_by(Task.deadline_at.asc().nulls_last(), Task.id)
        ).all()
    ]


def _workload(db: Session, user: User, rows: list[_Row]) -> list[CourseWorkload]:
    courses = db.scalars(
        select(Course)
        .where(Course.user_id == user.id, Course.archived_at.is_(None))
        .order_by(Course.name, Course.id)
    ).all()
    open_tasks: dict[uuid.UUID | None, int] = defaultdict(int)
    done_tasks: dict[uuid.UUID | None, int] = defaultdict(int)
    remaining: dict[uuid.UUID | None, int] = defaultdict(int)
    for task, _ in rows:
        if task.status == TaskStatus.COMPLETED:
            done_tasks[task.course_id] += 1
        else:
            open_tasks[task.course_id] += 1
            remaining[task.course_id] += task.remaining_minutes

    result = [
        CourseWorkload(
            course_id=course.id,
            name=course.name,
            code=course.code,
            color=course.color,
            open_tasks=open_tasks[course.id],
            completed_tasks=done_tasks[course.id],
            remaining_minutes=remaining[course.id],
        )
        for course in courses
    ]
    if open_tasks[None] or done_tasks[None]:
        result.append(
            CourseWorkload(
                course_id=None,
                name=_NO_COURSE,
                code=None,
                color=None,
                open_tasks=open_tasks[None],
                completed_tasks=done_tasks[None],
                remaining_minutes=remaining[None],
            )
        )
    return result


def _timed_rows(
    db: Session, user: User, start: datetime, now: datetime
) -> list[tuple[datetime, datetime, uuid.UUID | None]]:
    rows = db.execute(
        select(WorkInterval.started_at, WorkInterval.ended_at, Task.course_id)
        .join(StudySession, WorkInterval.session_id == StudySession.id)
        .join(Task, StudySession.task_id == Task.id)
        .where(
            WorkInterval.user_id == user.id,
            or_(WorkInterval.ended_at.is_(None), WorkInterval.ended_at > start),
            WorkInterval.started_at < now,
        )
    ).all()
    return [(max(s, start), min(e or now, now), course) for s, e, course in rows]


def _active_sessions(db: Session, user: User, start: datetime, end: datetime) -> list[StudySession]:
    return list(
        db.scalars(
            select(StudySession).where(
                StudySession.user_id == user.id,
                StudySession.status.in_(ACTIVE_STATUSES),
                StudySession.end_at > start,
                StudySession.start_at < end,
            )
        )
    )


def _minutes(session: StudySession) -> int:
    return int((session.end_at - session.start_at).total_seconds() // 60)


def _deadline_item(task: Task, course: Course | None) -> DeadlineItem:
    assert task.deadline_at is not None  # noqa: S101  # Callers select dated tasks.
    return DeadlineItem(
        task_id=task.id,
        title=task.title,
        task_type=task.task_type,
        deadline_at=task.deadline_at,
        course_name=course.name if course else None,
        course_color=course.color if course else None,
        remaining_minutes=task.remaining_minutes,
    )


def _attention(
    open_rows: list[_Row], sessions: list[StudySession], now: datetime
) -> list[AttentionItem]:
    items: list[AttentionItem] = []
    for task, course in open_rows:
        deadline = task.deadline_at
        if deadline is None or deadline > now + _ATTENTION_WINDOW:
            continue
        planned = sum(
            _minutes(s) for s in sessions if s.task_id == task.id and s.start_at < deadline
        )
        unplanned = max(task.remaining_minutes - planned, 0)
        if deadline <= now:
            reason = "overdue"
        elif unplanned:
            reason = "not_fully_planned"
        elif deadline <= now + _DUE_SOON:
            reason = "due_soon"
        else:
            continue
        items.append(
            AttentionItem(
                task_id=task.id,
                title=task.title,
                course_color=course.color if course else None,
                deadline_at=deadline,
                reason=reason,  # type: ignore[arg-type]
                unplanned_minutes=unplanned,
            )
        )
    order = {"overdue": 0, "not_fully_planned": 1, "due_soon": 2}
    return sorted(items, key=lambda item: (order[item.reason], item.deadline_at))


def attention(db: Session, user: User, now: datetime) -> list[AttentionItem]:
    """Open tasks that need a look: overdue, short of planned time, or due within 48 hours.

    The dashboard and notifications both use this, so they always agree.
    """
    open_rows = [row for row in _tasks(db, user) if row[0].status != TaskStatus.COMPLETED]
    return _attention(open_rows, _active_sessions(db, user, now, now + _ATTENTION_WINDOW), now)


def _daily_seconds(
    db: Session, user: User, first: date, zone: ZoneInfo, now: datetime
) -> dict[date, float]:
    per_day: dict[date, float] = defaultdict(float)
    for start, end, _ in _timed_rows(db, user, _start_of(first, zone), now):
        for day, seconds in _seconds_by_day(start, end, zone):
            per_day[day] += seconds
    return per_day


def _active_days(per_day: dict[date, float]) -> set[date]:
    return {day for day, seconds in per_day.items() if rounded_minutes(seconds) > 0}


def _goal(db: Session, user: User) -> int | None:
    preferences = db.get(StudyPreferences, user.id)
    return preferences.daily_goal_minutes if preferences else None


def _recent(db: Session, user: User, now: datetime) -> list[RecentSession]:
    """The last sessions the student finished, newest first, with the time they actually put in."""
    last_end = func.max(WorkInterval.ended_at).label("last_end")
    ended = db.execute(
        select(StudySession, Task, Course, last_end)
        .join(WorkInterval, WorkInterval.session_id == StudySession.id)
        .join(Task, StudySession.task_id == Task.id)
        .outerjoin(Course, Task.course_id == Course.id)
        .where(
            StudySession.user_id == user.id,
            StudySession.status == SessionStatus.COMPLETED,
        )
        .group_by(StudySession.id, Task.id, Course.id)
        .order_by(last_end.desc(), StudySession.id)
        .limit(_RECENT_SESSIONS)
    ).all()
    minutes = worked_minutes(db, [row[0].id for row in ended], now)
    return [
        RecentSession(
            session_id=session.id,
            task_id=task.id,
            task_title=task.title,
            course_name=course.name if course else None,
            course_color=course.color if course else None,
            ended_at=ended_at,
            minutes=minutes.get(session.id, 0),
        )
        for session, task, course, ended_at in ended
        if ended_at is not None
    ]


def dashboard(db: Session, user: User, now: datetime) -> DashboardRead:
    zone = ZoneInfo(user.timezone)
    today = now.astimezone(zone).date()
    today_start, today_end = local_day_bounds(today, zone)
    today_sessions = list_sessions(db, user, now, today_start, today_end)

    rows = _tasks(db, user)
    open_rows = [row for row in rows if row[0].status != TaskStatus.COMPLETED]
    future = [row for row in open_rows if row[0].deadline_at and row[0].deadline_at > now]
    exams = [row for row in future if row[0].task_type in EXAM_TYPES]
    assignments = [row for row in future if row[0].task_type not in EXAM_TYPES]

    horizon = now + _ATTENTION_WINDOW
    attention = _attention(open_rows, _active_sessions(db, user, now, horizon), now)

    monday = _week_start(today)
    week_start = _start_of(monday, zone)
    week_end = _start_of(monday + timedelta(days=7), zone)
    studied = sum(
        (end - start).total_seconds() for start, end, _ in _timed_rows(db, user, week_start, now)
    )
    planned = sum(
        _minutes(s)
        for s in _active_sessions(db, user, now, week_end)
        if s.status == SessionStatus.PLANNED
    )

    per_day = _daily_seconds(db, user, today - timedelta(days=_STREAK_LIMIT_DAYS - 1), zone, now)
    active = _active_days(per_day)

    return DashboardRead(
        today=today_sessions,
        upcoming_assignments=[_deadline_item(*r) for r in assignments[:_UPCOMING_LIMIT]],
        upcoming_exams=[_deadline_item(*r) for r in exams[:_UPCOMING_LIMIT]],
        attention=attention[:_ATTENTION_LIMIT],
        attention_total=len(attention),
        week=WeekSummary(
            week_start=monday, studied_minutes=rounded_minutes(studied), planned_minutes=planned
        ),
        tasks=TaskCounts(
            completed=len(rows) - len(open_rows),
            remaining=len(open_rows),
            overdue=sum(1 for t, _ in open_rows if t.deadline_at and t.deadline_at <= now),
        ),
        workload=_workload(db, user, rows),
        progress=TodayProgress(
            studied_minutes=rounded_minutes(per_day.get(today, 0)),
            goal_minutes=_goal(db, user),
            streak_days=_streak(active, today),
            studied_today=today in active,
        ),
        recent=_recent(db, user, now),
    )


def _minutes_per_course(
    db: Session,
    user: User,
    totals: dict[uuid.UUID | None, float],
) -> list[CourseMinutes]:
    ids = [course_id for course_id in totals if course_id is not None]
    courses = {c.id: c for c in db.scalars(select(Course).where(Course.id.in_(ids)))} if ids else {}
    result = [
        CourseMinutes(
            course_id=course_id,
            name=courses[course_id].name if course_id else _NO_COURSE,
            color=courses[course_id].color if course_id else None,
            minutes=rounded_minutes(seconds),
        )
        for course_id, seconds in totals.items()
    ]
    return sorted(
        (item for item in result if item.minutes > 0),
        key=lambda item: (-item.minutes, item.name),
    )


def _streak(active: set[date], today: date) -> int:
    """Consecutive days of study. Today only counts once it has happened, so it cannot break it."""
    day = today if today in active else today - timedelta(days=1)
    length = 0
    while day in active and length < _STREAK_LIMIT_DAYS:
        length += 1
        day -= timedelta(days=1)
    return length


def _consistency(
    db: Session,
    user: User,
    per_day: dict[date, float],
    today: date,
    zone: ZoneInfo,
    now: datetime,
) -> Consistency:
    days = [today - timedelta(days=i) for i in range(_CONSISTENCY_DAYS - 1, -1, -1)]
    minutes = {day: rounded_minutes(per_day.get(day, 0)) for day in days}
    active = {day for day, value in minutes.items() if value > 0}
    statuses = db.scalars(
        select(StudySession.status).where(
            StudySession.user_id == user.id,
            StudySession.status.in_((SessionStatus.COMPLETED, SessionStatus.MISSED)),
            StudySession.end_at >= _start_of(days[0], zone),
            StudySession.start_at < now,
        )
    ).all()
    return Consistency(
        days=[ConsistencyDay(date=day, minutes=minutes[day]) for day in days],
        active_days=len(active),
        # Counted over the same longer history as the dashboard, so the two never disagree.
        current_streak=_streak(
            _active_days(
                _daily_seconds(db, user, today - timedelta(days=_STREAK_LIMIT_DAYS - 1), zone, now)
            ),
            today,
        ),
        sessions_completed=sum(1 for s in statuses if s == SessionStatus.COMPLETED),
        sessions_missed=sum(1 for s in statuses if s == SessionStatus.MISSED),
    )


def _upcoming(
    open_rows: list[_Row], sessions: list[StudySession], today: date, zone: ZoneInfo
) -> list[UpcomingDay]:
    planned: dict[date, int] = defaultdict(int)
    for session in sessions:
        planned[session.start_at.astimezone(zone).date()] += _minutes(session)
    deadlines: dict[date, int] = defaultdict(int)
    for task, _ in open_rows:
        if task.deadline_at is not None:
            deadlines[task.deadline_at.astimezone(zone).date()] += 1
    days = [today + timedelta(days=i) for i in range(_UPCOMING_DAYS)]
    return [UpcomingDay(date=d, planned_minutes=planned[d], deadlines=deadlines[d]) for d in days]


def _estimates(rows: list[_Row], since: datetime) -> EstimateSummary:
    finished = sorted(
        (
            task
            for task, _ in rows
            if task.status == TaskStatus.COMPLETED
            and task.actual_minutes > 0
            and task.completed_at is not None
            and task.completed_at >= since
        ),
        key=lambda task: (task.completed_at, task.id),
        reverse=True,
    )
    return EstimateSummary(
        tasks_compared=len(finished),
        estimated_minutes=sum(t.estimated_minutes for t in finished),
        actual_minutes=sum(t.actual_minutes for t in finished),
        recent=[
            EstimateComparison(
                task_id=t.id,
                title=t.title,
                estimated_minutes=t.estimated_minutes,
                actual_minutes=t.actual_minutes,
            )
            for t in finished[:_RECENT_ESTIMATES]
        ],
    )


def analytics(db: Session, user: User, now: datetime, weeks: int) -> AnalyticsRead:
    reconcile_missed_sessions(db, user, now)
    zone = ZoneInfo(user.timezone)
    today = now.astimezone(zone).date()
    this_week = _week_start(today)
    mondays = [this_week - timedelta(weeks=i) for i in range(weeks - 1, -1, -1)]
    range_start = _start_of(mondays[0], zone)
    earliest_day = min(mondays[0], today - timedelta(days=_CONSISTENCY_DAYS - 1))

    per_day: dict[date, float] = defaultdict(float)
    per_week: dict[date, float] = defaultdict(float)
    per_course: dict[uuid.UUID | None, float] = defaultdict(float)
    for start, end, course_id in _timed_rows(db, user, _start_of(earliest_day, zone), now):
        for day, seconds in _seconds_by_day(start, end, zone):
            per_day[day] += seconds
            if day >= mondays[0]:
                per_week[_week_start(day)] += seconds
                per_course[course_id] += seconds

    rows = _tasks(db, user)
    open_rows = [row for row in rows if row[0].status != TaskStatus.COMPLETED]

    completions: dict[date, int] = defaultdict(int)
    for task, _ in rows:
        if task.completed_at is not None and task.completed_at >= range_start:
            completions[_week_start(task.completed_at.astimezone(zone).date())] += 1

    upcoming_end = _start_of(today + timedelta(days=_UPCOMING_DAYS), zone)
    return AnalyticsRead(
        weekly_minutes=[
            WeekMinutes(week_start=m, minutes=rounded_minutes(per_week[m])) for m in mondays
        ],
        minutes_per_course=_minutes_per_course(db, user, per_course),
        completions=[WeekCount(week_start=m, count=completions[m]) for m in mondays],
        workload=[w for w in _workload(db, user, rows) if w.remaining_minutes > 0],
        estimates=_estimates(rows, range_start),
        upcoming=_upcoming(open_rows, _active_sessions(db, user, now, upcoming_end), today, zone),
        consistency=_consistency(db, user, per_day, today, zone, now),
    )


def month(db: Session, user: User, now: datetime, first: date | None) -> MonthRead:
    """Each day of one local month: time studied by task, tasks finished and deadlines."""
    zone = ZoneInfo(user.timezone)
    first = (first or now.astimezone(zone).date()).replace(day=1)
    following = (first + timedelta(days=32)).replace(day=1)
    start, end = _start_of(first, zone), _start_of(following, zone)

    studied: dict[date, dict[uuid.UUID, float]] = defaultdict(lambda: defaultdict(float))
    rows = db.execute(
        select(WorkInterval.started_at, WorkInterval.ended_at, Task.id)
        .join(StudySession, WorkInterval.session_id == StudySession.id)
        .join(Task, StudySession.task_id == Task.id)
        .where(
            WorkInterval.user_id == user.id,
            or_(WorkInterval.ended_at.is_(None), WorkInterval.ended_at > start),
            WorkInterval.started_at < min(end, now),
        )
    ).all()
    for started, ended, task_id in rows:
        clipped = (max(started, start), min(ended or now, now, end))
        for day, seconds in _seconds_by_day(*clipped, zone):
            studied[day][task_id] += seconds

    tasks = {task.id: (task, course) for task, course in _tasks(db, user)}
    # Time on a task in an archived course still happened, so look those tasks up too.
    missing = {t for per_task in studied.values() for t in per_task if t not in tasks}
    if missing:
        for task, course in db.execute(
            select(Task, Course)
            .outerjoin(Course, Task.course_id == Course.id)
            .where(Task.id.in_(missing))
        ).all():
            tasks[task.id] = (task, course)

    completed: dict[date, list[DayItem]] = defaultdict(list)
    deadlines: dict[date, list[DayDeadline]] = defaultdict(list)
    for task, course in tasks.values():
        color = course.color if course else None
        if task.completed_at is not None and start <= task.completed_at < end:
            completed[task.completed_at.astimezone(zone).date()].append(
                DayItem(task_id=task.id, title=task.title, course_color=color)
            )
        if task.deadline_at is not None and start <= task.deadline_at < end:
            deadlines[task.deadline_at.astimezone(zone).date()].append(
                DayDeadline(
                    task_id=task.id,
                    title=task.title,
                    task_type=task.task_type,
                    deadline_at=task.deadline_at,
                    course_color=color,
                    completed=task.status == TaskStatus.COMPLETED,
                )
            )

    days: list[MonthDay] = []
    day = first
    while day < following:
        by_task = []
        for task_id, seconds in studied[day].items():
            task, course = tasks[task_id]
            if rounded_minutes(seconds) > 0:
                by_task.append(
                    DayTask(
                        task_id=task_id,
                        title=task.title,
                        course_color=course.color if course else None,
                        minutes=rounded_minutes(seconds),
                    )
                )
        days.append(
            MonthDay(
                date=day,
                studied_minutes=rounded_minutes(sum(studied[day].values())),
                studied=sorted(by_task, key=lambda item: (-item.minutes, item.title)),
                completed=sorted(completed[day], key=lambda item: item.title),
                deadlines=sorted(deadlines[day], key=lambda item: item.deadline_at),
            )
        )
        day += timedelta(days=1)
    return MonthRead(month=first, goal_minutes=_goal(db, user), days=days)
