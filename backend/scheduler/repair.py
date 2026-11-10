"""Adapting an existing schedule while changing as little as possible.

Rebuilding from scratch can reshuffle a whole month because one session was missed. Repair keeps
every session that is still valid and only finds time for what is actually affected. It touches
other sessions only when that is the only way to meet a deadline.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from scheduler.models import (
    ChangeKind,
    ExistingSession,
    Interval,
    Placement,
    PlanRequest,
    PlanResult,
    RepairReason,
    RepairResult,
    RiskReason,
    SessionChange,
    SessionClass,
    TaskInput,
    UnplacedTask,
)
from scheduler.planner import plan
from scheduler.timeline import expand_rules, merge_intervals

_FAR_FUTURE = 10**12


def _minutes(session: ExistingSession) -> int:
    return int((session.end - session.start).total_seconds() // 60)


def _shortfall(result: PlanResult) -> int:
    return sum(
        item.shortfall_minutes
        for item in result.at_risk
        if item.reason is RiskReason.INSUFFICIENT_TIME
    )


def _inside_any(session: ExistingSession, intervals: Iterable[Interval]) -> bool:
    return any(i.start <= session.start and session.end <= i.end for i in intervals)


def _overlaps_any(session: ExistingSession, intervals: Iterable[Interval]) -> bool:
    return any(session.start < i.end and i.start < session.end for i in intervals)


@dataclass
class _Removal:
    session: ExistingSession
    reason: RepairReason
    sticky_released: bool = False


class _Repair:
    def __init__(self, request: PlanRequest) -> None:
        self.request = request
        self.zone = ZoneInfo(request.timezone)
        self.preferences = request.preferences
        self.tasks: dict[str, TaskInput] = {task.id: task for task in request.tasks}
        self.locked = self._of_class(SessionClass.LOCKED)
        self.sticky = self._of_class(SessionClass.STICKY)
        self.flexible = self._of_class(SessionClass.FLEXIBLE)
        self.removed: dict[str, _Removal] = {}
        self.resized: dict[str, datetime] = {}
        self.originals = {s.id: s for s in request.existing_sessions}
        # What a plan from scratch would do; the yardstick for how much effort repair may spend.
        self.fresh = plan(replace(request, existing_sessions=(*self.locked, *self.sticky)))
        self.fresh_minutes: dict[str, int] = defaultdict(int)
        for placement in self.fresh.placements:
            self.fresh_minutes[placement.task_id] += placement.minutes
        self._kept_in_fresh: dict[str, int] = defaultdict(int)
        for session in (*self.locked, *self.sticky):
            self._kept_in_fresh[session.task_id] += _minutes(session)

    def _of_class(self, session_class: SessionClass) -> list[ExistingSession]:
        return sorted(
            (s for s in self.request.existing_sessions if s.session_class is session_class),
            key=lambda s: (s.start, s.id),
        )

    # --- Keeping what is still valid -----------------------------------------------------------

    def _invalid_reason(
        self, session: ExistingSession, windows: list[Interval], blocked: list[Interval]
    ) -> RepairReason | None:
        task = self.tasks.get(session.task_id)
        if task is None or task.remaining_minutes <= 0:
            return RepairReason.TASK_FINISHED
        if task.deadline is not None and session.end > task.deadline:
            return RepairReason.PAST_DEADLINE
        if not _inside_any(session, windows):
            return RepairReason.OUTSIDE_AVAILABILITY
        if _overlaps_any(session, blocked):
            return RepairReason.TIME_BLOCKED
        if _minutes(session) > self.preferences.preferred_session_minutes:
            return RepairReason.SCHEDULE_RULES
        return None

    def _drop_invalid(self) -> list[ExistingSession]:
        last_end = max(
            (s.end for s in self.request.existing_sessions), default=self.request.horizon_end
        )
        span_end = max(last_end, self.request.horizon_end)
        windows = expand_rules(self.request.windows, self.request.now, span_end, self.zone)
        margin = timedelta(minutes=self.preferences.break_minutes)
        blocked = merge_intervals(
            [
                *expand_rules(self.request.weekly_blocks, self.request.now, span_end, self.zone),
                *self.request.one_off_blocks,
                *(Interval(s.start - margin, s.end + margin) for s in (*self.locked, *self.sticky)),
            ]
        )

        kept: list[ExistingSession] = []
        for session in self.flexible:
            reason = self._invalid_reason(session, windows, blocked)
            if reason is None:
                kept.append(session)
            else:
                self.removed[session.id] = _Removal(session, reason)
        return self._drop_rule_breakers(kept, margin)

    def _drop_rule_breakers(
        self, sessions: list[ExistingSession], margin: timedelta
    ) -> list[ExistingSession]:
        """Preferences may have changed since these were planned. Earlier sessions win."""
        day_totals: dict[object, int] = defaultdict(int)
        day_totals[self.request.now.astimezone(self.zone).date()] = (
            self.request.studied_today_minutes
        )
        for session in (*self.locked, *self.sticky):
            day_totals[session.start.astimezone(self.zone).date()] += _minutes(session)

        kept: list[ExistingSession] = []
        for session in sessions:
            day = session.start.astimezone(self.zone).date()
            if kept and session.start - kept[-1].end < margin:
                self.removed[session.id] = _Removal(session, RepairReason.SCHEDULE_RULES)
            elif day_totals[day] + _minutes(session) > self.preferences.max_daily_minutes:
                self.removed[session.id] = _Removal(session, RepairReason.DAILY_LIMIT)
            else:
                day_totals[day] += _minutes(session)
                kept.append(session)
        return kept

    def _trim_surplus(self, sessions: list[ExistingSession]) -> list[ExistingSession]:
        """If less work remains than is scheduled, take it from the latest sessions."""
        planned: dict[str, int] = defaultdict(int)
        for session in (*self.locked, *self.sticky, *sessions):
            planned[session.task_id] += _minutes(session)

        result: list[ExistingSession] = []
        for session in reversed(sessions):
            surplus = planned[session.task_id] - self.tasks[session.task_id].remaining_minutes
            length = _minutes(session)
            if surplus <= 0:
                result.append(session)
            elif length <= surplus:
                planned[session.task_id] -= length
                self.removed[session.id] = _Removal(session, RepairReason.LESS_WORK_NEEDED)
            else:
                shorter = length - surplus
                planned[session.task_id] -= surplus
                new_end = session.start + timedelta(minutes=shorter)
                self.resized[session.id] = new_end
                result.append(replace(session, end=new_end))
        result.reverse()
        return result

    # --- Finding time for the rest -------------------------------------------------------------

    def _plan_around(
        self, flexible: list[ExistingSession], sticky: list[ExistingSession] | None = None
    ) -> PlanResult:
        keep_sticky = self.sticky if sticky is None else sticky
        # Retained sessions behave as fixed for this plan, so only the deficit gets placed.
        fixed = [replace(s, session_class=SessionClass.STICKY) for s in flexible]
        return plan(
            replace(
                self.request,
                tasks=self._tasks_with_open_ended_work_capped(flexible, keep_sticky),
                existing_sessions=(*self.locked, *keep_sticky, *fixed),
            )
        )

    def _is_open_ended(self, task: TaskInput) -> bool:
        return task.deadline is None or task.deadline > self.request.horizon_end

    def _protected_minutes(
        self, flexible: list[ExistingSession], sticky: list[ExistingSession]
    ) -> dict[str, int]:
        minutes: dict[str, int] = defaultdict(int)
        for session in (*self.locked, *sticky, *flexible):
            minutes[session.task_id] += _minutes(session)
        return minutes

    def _tasks_with_open_ended_work_capped(
        self, flexible: list[ExistingSession], sticky: list[ExistingSession]
    ) -> tuple[TaskInput, ...]:
        """Work with no near deadline is never "behind", so it only tops up to a fresh plan's share.

        Without this cap, each update would find free time and add yet more sessions for it.
        """
        held = self._protected_minutes(flexible, sticky)
        tasks: list[TaskInput] = []
        for task in self.request.tasks:
            if self._is_open_ended(task):
                wanted = self.fresh_minutes[task.id] + self._kept_in_fresh[task.id]
                tasks.append(
                    replace(
                        task,
                        remaining_minutes=max(held[task.id], min(wanted, task.remaining_minutes)),
                        # Its deadline is beyond this plan. Without one, its share is placed in
                        # full rather than scaled down a second time.
                        deadline=None,
                    )
                )
            else:
                tasks.append(task)
        return tuple(tasks)

    def _open_ended_unplaced(
        self,
        flexible: list[ExistingSession],
        sticky: list[ExistingSession],
        result: PlanResult,
    ) -> tuple[UnplacedTask, ...]:
        placed = self._protected_minutes(flexible, sticky)
        for placement in result.placements:
            placed[placement.task_id] += placement.minutes
        return tuple(
            UnplacedTask(task.id, task.remaining_minutes - placed[task.id])
            for task in sorted(self.request.tasks, key=lambda t: t.id)
            if self._is_open_ended(task) and task.remaining_minutes > placed[task.id]
        )

    def _fill_remaining_gaps(
        self, retained: list[ExistingSession], sticky: list[ExistingSession], result: PlanResult
    ) -> PlanResult:
        """Plan around the new sessions until nothing more fits.

        A single pass can leave a usable slot empty, because pacing or the guard held it back for
        work that ended up elsewhere. Repeating here means a second update has nothing left to do.
        """
        placements = list(result.placements)
        while result.placements:
            placed = [
                ExistingSession(f"new-{i}", p.task_id, p.start, p.end, SessionClass.FLEXIBLE)
                for i, p in enumerate(placements)
            ]
            result = self._plan_around([*retained, *placed], sticky)
            placements.extend(result.placements)
        return replace(result, placements=tuple(placements))

    def _release(self, session: ExistingSession, *, sticky_released: bool = False) -> None:
        original = self.originals[session.id]
        self.resized.pop(session.id, None)
        self.removed[session.id] = _Removal(
            original, RepairReason.MAKING_ROOM, sticky_released=sticky_released
        )

    def _deadline_key(self, session: ExistingSession) -> float:
        deadline = self.tasks[session.task_id].deadline
        return _FAR_FUTURE if deadline is None else deadline.timestamp()

    def _release_order(
        self, sessions: list[ExistingSession], result: PlanResult
    ) -> list[ExistingSession]:
        """Which sessions to free first: least-urgent work placed before the failing deadline."""
        failing = [
            deadline
            for item in result.at_risk
            if item.reason is RiskReason.INSUFFICIENT_TIME
            and (deadline := self.tasks[item.task_id].deadline) is not None
        ]
        earliest = min(failing, default=None)
        pool = [s for s in sessions if earliest is None or s.start < earliest] or sessions
        return sorted(pool, key=lambda s: (-self._deadline_key(s), -s.start.timestamp(), s.id))

    def run(self) -> RepairResult:
        retained = self._trim_surplus(self._drop_invalid())
        result = self._plan_around(retained)

        # Only disturb valid sessions if doing so can actually save more work.
        target = _shortfall(self.fresh)
        batch = 1
        while retained and _shortfall(result) > target:
            for session in self._release_order(retained, result)[:batch]:
                retained.remove(session)
                self._release(session)
            batch *= 2
            result = self._plan_around(retained) if retained else self.fresh

        # The student's own edits are given up last, and each one is flagged in the preview.
        sticky = list(self.sticky)
        if _shortfall(result) > 0 and sticky:
            without_sticky = plan(replace(self.request, existing_sessions=tuple(self.locked)))
            batch = 1
            while sticky and _shortfall(result) > _shortfall(without_sticky):
                for session in self._release_order(sticky, result)[:batch]:
                    sticky.remove(session)
                    self._release(session, sticky_released=True)
                batch *= 2
                result = self._plan_around(retained, sticky=sticky)

        result = self._fill_remaining_gaps(retained, sticky, result)
        result = replace(result, unplaced=self._open_ended_unplaced(retained, sticky, result))
        return build_result(self.request, self.removed, self.resized, result)


def build_result(
    request: PlanRequest,
    removed: dict[str, _Removal],
    resized: dict[str, datetime],
    result: PlanResult,
) -> RepairResult:
    """Describe the difference, pairing removals with new sessions of the same task as moves."""
    placements = list(result.placements)
    remaining_removals = dict(removed)

    # A released session that lands exactly where it was has not changed at all.
    for placement in list(placements):
        for session_id, removal in list(remaining_removals.items()):
            session = removal.session
            if (session.task_id, session.start, session.end) == (
                placement.task_id,
                placement.start,
                placement.end,
            ):
                del remaining_removals[session_id]
                placements.remove(placement)
                break

    new_by_task: dict[str, list[Placement]] = defaultdict(list)
    for placement in sorted(placements, key=lambda p: p.start):
        new_by_task[placement.task_id].append(placement)

    changes: list[SessionChange] = []
    ordered = sorted(remaining_removals.values(), key=lambda r: (r.session.start, r.session.id))
    for removal in ordered:
        session = removal.session
        waiting = new_by_task[session.task_id]
        before = Interval(session.start, session.end)
        if waiting:
            target = waiting.pop(0)
            changes.append(
                SessionChange(
                    kind=ChangeKind.MOVE,
                    task_id=session.task_id,
                    session_id=session.id,
                    before=before,
                    after=Interval(target.start, target.end),
                    reason=removal.reason,
                    explanation=target.explanation,
                    sticky_released=removal.sticky_released,
                )
            )
        else:
            changes.append(
                SessionChange(
                    kind=ChangeKind.REMOVE,
                    task_id=session.task_id,
                    session_id=session.id,
                    before=before,
                    reason=removal.reason,
                    sticky_released=removal.sticky_released,
                )
            )

    sessions_by_id = {s.id: s for s in request.existing_sessions}
    for session_id, new_end in resized.items():
        session = sessions_by_id[session_id]
        changes.append(
            SessionChange(
                kind=ChangeKind.RESIZE,
                task_id=session.task_id,
                session_id=session_id,
                before=Interval(session.start, session.end),
                after=Interval(session.start, new_end),
                reason=RepairReason.LESS_WORK_NEEDED,
            )
        )

    for waiting in new_by_task.values():
        for placement in waiting:
            changes.append(
                SessionChange(
                    kind=ChangeKind.CREATE,
                    task_id=placement.task_id,
                    after=Interval(placement.start, placement.end),
                    explanation=placement.explanation,
                )
            )

    def change_order(change: SessionChange) -> tuple[datetime, str]:
        when = change.after or change.before
        assert when is not None  # noqa: S101  # Every change has one or the other.
        return (when.start, change.session_id or change.task_id)

    changes.sort(key=change_order)
    touched = len(remaining_removals) + len(resized)
    return RepairResult(
        changes=tuple(changes),
        unchanged=len(request.existing_sessions) - touched,
        at_risk=result.at_risk,
        unplaced=result.unplaced,
    )


def repair(request: PlanRequest) -> RepairResult:
    """Adapt the schedule, keeping unaffected sessions. The default way to update a plan."""
    return _Repair(request).run()


def rebuild(request: PlanRequest) -> RepairResult:
    """Replace every flexible session. Locked and student-edited sessions are still kept."""
    tasks = {task.id for task in request.tasks}
    removed = {
        session.id: _Removal(
            session,
            RepairReason.REBUILT if session.task_id in tasks else RepairReason.TASK_FINISHED,
        )
        for session in request.existing_sessions
        if session.session_class is SessionClass.FLEXIBLE
    }
    return build_result(request, removed, {}, plan(request))
