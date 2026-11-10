"""The planning algorithm. docs/SCHEDULING_ENGINE.md explains the reasoning.

In short: a weighted score chooses what is good for each slot, and a simulation of
earliest-deadline-first (EDF) vetoes any choice that would make a deadline unreachable.
"""

import bisect
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from typing import Final
from zoneinfo import ZoneInfo

from scheduler.models import (
    AtRiskTask,
    ExistingSession,
    Explanation,
    Placement,
    PlanRequest,
    PlanResult,
    Reason,
    RiskReason,
    SessionClass,
    TaskInput,
    UnplacedTask,
)
from scheduler.timeline import Slot, Timeline, build_timeline

WEIGHTS: Final = {"urgency": 0.50, "priority": 0.25, "course_balance": 0.15, "variety": 0.10}
_MAX_CANDIDATES: Final = 5
_BALANCE_WINDOW_DAYS: Final = 7
_REASON_FOR_FACTOR: Final = {
    "urgency": Reason.DEADLINE_PRESSURE,
    "priority": Reason.HIGH_PRIORITY,
    "course_balance": Reason.COURSE_BALANCE,
    "variety": Reason.VARIETY,
}


def usable_minutes(remaining: int, capacity: int, minimum: int) -> int:
    """How much of `remaining` to place in a gap of `capacity`. Zero means it does not fit.

    Sessions below the minimum are avoided, except a task's final bit of work. If this session
    would leave too little for a later one, it gives some of its time to that later session.
    """
    if remaining <= capacity:
        return remaining
    if capacity < minimum:
        return 0
    if remaining - capacity < minimum and remaining - minimum >= minimum:
        return remaining - minimum
    return capacity


@dataclass
class _Task:
    index: int
    id: str
    course: str
    priority: int
    real_deadline: int | None  # None when undated.
    deadline: int | None  # What planning currently aims for; earlier if buffered.
    demand: int
    guarded: bool  # Its deadline is protected by the guard.
    at_risk: bool = False


class _Planner:
    def __init__(self, request: PlanRequest) -> None:
        self.request = request
        self.timeline: Timeline = build_timeline(request)
        self.slots: tuple[Slot, ...] = self.timeline.slots
        self.minimum = request.preferences.min_session_minutes
        self.horizon = self.timeline.to_minutes(request.horizon_end)
        self.starts = [slot.start for slot in self.slots]
        self.capacity_before = self._cumulative_capacity()
        self.overdue: list[tuple[str, int]] = []
        self.pinned_minutes_by_day_course: dict[tuple[int, str], int] = defaultdict(int)
        self.tasks = self._prepare_tasks()
        self.guard_order: list[_Task] = []

    # --- Setup ---------------------------------------------------------------------------------

    def _prepare_tasks(self) -> list[_Task]:
        pinned_by_task: dict[str, int] = defaultdict(int)
        tasks_by_id = {task.id: task for task in self.request.tasks}
        for session in self.request.existing_sessions:
            if session.session_class is SessionClass.FLEXIBLE:
                continue
            minutes = int((session.end - session.start).total_seconds() // 60)
            pinned_by_task[session.task_id] += minutes
            source = tasks_by_id.get(session.task_id)
            if source is not None:
                day = self._local_day_index(session)
                self.pinned_minutes_by_day_course[(day, self._course_key(source))] += minutes

        buffer = self.request.preferences.deadline_buffer_hours * 60
        prepared: list[_Task] = []
        # Sorted so that the order tasks arrive in can never affect the result.
        for source in sorted(self.request.tasks, key=lambda task: task.id):
            demand = source.remaining_minutes - pinned_by_task[source.id]
            if demand <= 0:
                continue
            real = None if source.deadline is None else self.timeline.to_minutes(source.deadline)
            if real is not None and real <= 0:
                self.overdue.append((source.id, demand))
                continue
            buffered = real
            if real is not None and real - buffer > 0:
                buffered = real - buffer
            prepared.append(
                _Task(
                    index=len(prepared),
                    id=source.id,
                    course=self._course_key(source),
                    priority=source.priority,
                    real_deadline=real,
                    deadline=buffered,
                    demand=demand,
                    guarded=real is not None and real <= self.horizon,
                )
            )
        return prepared

    @staticmethod
    def _course_key(task: TaskInput) -> str:
        return task.course_id if task.course_id is not None else f"task:{task.id}"

    def _local_day_index(self, session: ExistingSession) -> int:
        local = session.start.astimezone(ZoneInfo(self.request.timezone)).date()
        return (local - self.timeline.first_day).days

    def _cumulative_capacity(self) -> list[int]:
        """Study minutes available before each slot, respecting each day's limit."""
        totals = [0]
        day_used: dict[int, int] = defaultdict(int)
        for slot in self.slots:
            available = max(self.timeline.day_budgets[slot.day] - day_used[slot.day], 0)
            taken = min(slot.minutes, available)
            day_used[slot.day] += taken
            totals.append(totals[-1] + taken)
        return totals

    def _capacity_between(self, slot_index: int, end: int) -> int:
        last = bisect.bisect_left(self.starts, end)
        return max(self.capacity_before[last] - self.capacity_before[slot_index], 0)

    # --- EDF simulation ------------------------------------------------------------------------

    def _usable(self, task: _Task, remaining: int, slot: Slot, day_left: int) -> int:
        end = slot.end if task.deadline is None else min(slot.end, task.deadline)
        capacity = min(end - slot.start, day_left)
        return usable_minutes(remaining, capacity, self.minimum) if capacity > 0 else 0

    def _set_guard_order(self) -> None:
        self.guard_order = sorted(
            (task for task in self.tasks if task.guarded and not task.at_risk),
            key=lambda task: (task.deadline, task.id),
        )

    def _simulate(
        self, first_slot: int, remaining: list[int], day_used: list[int]
    ) -> list[tuple[_Task, int]]:
        """Run EDF from `first_slot`. Returns each guarded task that finishes late, and by how much.

        `remaining` and `day_used` are the caller's own copies and are modified here.
        """
        order = [task for task in self.guard_order if remaining[task.index] > 0]
        late: list[tuple[_Task, int]] = []
        budgets = self.timeline.day_budgets
        for slot in self.slots[first_slot:]:
            if not order:
                return late
            while order and order[0].deadline <= slot.start:  # type: ignore[operator]
                expired = order.pop(0)
                late.append((expired, remaining[expired.index]))
            day_left = budgets[slot.day] - day_used[slot.day]
            if day_left <= 0:
                continue
            for position, task in enumerate(order):
                take = self._usable(task, remaining[task.index], slot, day_left)
                if take > 0:
                    remaining[task.index] -= take
                    day_used[slot.day] += take
                    if remaining[task.index] == 0:
                        order.pop(position)
                    break
        late.extend((task, remaining[task.index]) for task in order)
        return late

    def _late_from_start(self) -> list[tuple[_Task, int]]:
        remaining = [task.demand for task in self.tasks]
        return self._simulate(0, remaining, [0] * len(self.timeline.day_budgets))

    def _settle_deadlines(self) -> None:
        """Decide which deadlines the guard protects, and which keep their early-finish margin."""
        margins = {task.index: task.deadline for task in self.tasks}

        # First find what cannot be saved even with no margins, so that a hopeless task
        # cannot cost every other task its margin.
        for task in self.tasks:
            task.deadline = task.real_deadline
        self._set_guard_order()
        late = self._late_from_start()
        while late:
            cutoff = min(task.deadline for task, _ in late)  # type: ignore[type-var]
            pool = [t for t in self.guard_order if t.deadline <= cutoff]  # type: ignore[operator]
            victim = min(pool, key=lambda t: (t.priority, -t.demand, t.id))
            victim.at_risk = True
            self._set_guard_order()
            late = self._late_from_start()

        for task in self.tasks:
            if not task.at_risk:
                task.deadline = margins[task.index]
        self._set_guard_order()
        late = self._late_from_start()

        # Prefer finishing early, but only the tasks that cannot manage it lose their margin.
        while relaxable := [t for t, _ in late if t.deadline != t.real_deadline]:
            for task in relaxable:
                task.deadline = task.real_deadline
            self._set_guard_order()
            late = self._late_from_start()

        # Mixed margins can still crowd out a task. Without margins everything left fits.
        if late:
            for task in self.tasks:
                task.deadline = task.real_deadline
            self._set_guard_order()

    # --- Pacing --------------------------------------------------------------------------------

    def _pace_targets(self) -> list[float]:
        """A cumulative soft target of study minutes by the end of each day."""
        day_count = len(self.timeline.day_budgets)
        daily = [0.0] * day_count
        for task in self.tasks:
            end = self.horizon if task.deadline is None else min(task.deadline, self.horizon)
            days = sorted({slot.day for slot in self.slots if slot.start < end})
            if not days:
                continue
            for day in days:
                daily[day] += self._scaled_demand(task) / len(days)
        totals: list[float] = []
        running = 0.0
        for value in daily:
            running += value
            totals.append(running)
        return totals

    def _scaled_demand(self, task: _Task) -> float:
        """For a deadline past the horizon, only a proportional share is due within it."""
        if task.real_deadline is None or task.real_deadline <= self.horizon:
            return float(task.demand)
        return task.demand * self.horizon / task.real_deadline

    # --- Scoring -------------------------------------------------------------------------------

    def _factors(
        self,
        task: _Task,
        slot_index: int,
        remaining: int,
        day_course: dict[tuple[int, str], int],
        day_task_sessions: dict[tuple[int, int], int],
    ) -> dict[str, float]:
        slot = self.slots[slot_index]
        if task.real_deadline is None:
            urgency = 0.0
        else:
            end = min(task.deadline or task.real_deadline, self.horizon)
            capacity = self._capacity_between(slot_index, end)
            share = remaining if task.guarded else remaining * self.horizon / task.real_deadline
            urgency = min(share / capacity, 1.0) if capacity > 0 else 1.0

        window = range(max(slot.day - _BALANCE_WINDOW_DAYS + 1, 0), slot.day + 1)
        course_minutes = sum(day_course[(day, task.course)] for day in window)
        all_minutes = sum(v for (day, _), v in day_course.items() if day in window)
        balance = 1.0 - course_minutes / all_minutes if all_minutes else 1.0
        variety = 1.0 / (1 + day_task_sessions[(slot.day, task.index)])

        return {
            "urgency": round(urgency, 6),
            "priority": round((task.priority - 1) / 3, 6),
            "course_balance": round(balance, 6),
            "variety": round(variety, 6),
        }

    @staticmethod
    def _score(factors: dict[str, float]) -> float:
        return sum(WEIGHTS[name] * value for name, value in factors.items())

    # --- Main loop -----------------------------------------------------------------------------

    def _late_after(
        self,
        slot_index: int,
        choice: tuple[_Task, int] | None,
        remaining: list[int],
        day_used: list[int],
    ) -> int:
        """Total minutes late if `choice` takes this slot and EDF handles everything after it."""
        if not self.guard_order:
            return 0
        trial_remaining = remaining.copy()
        trial_used = day_used.copy()
        if choice is not None:
            task, take = choice
            trial_remaining[task.index] -= take
            trial_used[self.slots[slot_index].day] += take
        late = self._simulate(slot_index + 1, trial_remaining, trial_used)
        return sum(minutes for _, minutes in late)

    def run(self) -> PlanResult:
        self._settle_deadlines()
        targets = self._pace_targets()
        budgets = self.timeline.day_budgets
        remaining = [task.demand for task in self.tasks]
        day_used = [0] * len(budgets)
        day_course: dict[tuple[int, str], int] = defaultdict(int)
        day_course.update(self.pinned_minutes_by_day_course)
        day_task_sessions: dict[tuple[int, int], int] = defaultdict(int)
        placed_total = 0
        placements: list[Placement] = []

        for index, slot in enumerate(self.slots):
            day_left = budgets[slot.day] - day_used[slot.day]
            if day_left <= 0:
                continue

            options: list[tuple[_Task, int]] = []
            for task in self.tasks:
                if remaining[task.index] > 0:
                    take = self._usable(task, remaining[task.index], slot, day_left)
                    if take > 0:
                        options.append((task, take))
            if not options:
                continue

            edf_choice = next(
                (
                    option
                    for guarded in self.guard_order
                    for option in options
                    if option[0] is guarded
                ),
                None,
            )
            baseline = self._late_after(index, edf_choice, remaining, day_used)

            ahead_of_pace = placed_total >= targets[slot.day]
            at_risk_waiting = any(task.at_risk for task, _ in options)
            if (
                ahead_of_pace
                and not at_risk_waiting
                and self._late_after(index, None, remaining, day_used) <= baseline
            ):
                continue

            factors = {
                task.index: self._factors(
                    task, index, remaining[task.index], day_course, day_task_sessions
                )
                for task, _ in options
            }
            ranked = sorted(
                options,
                key=lambda option: (
                    -self._score(factors[option[0].index]),
                    (option[0].real_deadline if option[0].real_deadline is not None else 10**12),
                    option[0].id,
                ),
            )

            chosen: tuple[_Task, int] | None = None
            for option in ranked[:_MAX_CANDIDATES]:
                if option is edf_choice or (
                    self._late_after(index, option, remaining, day_used) <= baseline
                ):
                    chosen = option
                    break
            if chosen is None:
                chosen = edf_choice
            if chosen is None:
                continue

            task, take = chosen
            remaining[task.index] -= take
            day_used[slot.day] += take
            placed_total += take
            day_course[(slot.day, task.course)] += take
            day_task_sessions[(slot.day, task.index)] += 1
            placements.append(
                Placement(
                    task_id=task.id,
                    start=self.timeline.to_instant(slot.start),
                    end=self.timeline.to_instant(slot.start + take),
                    explanation=self._explain(
                        task, factors[task.index], guard_override=chosen is not ranked[0]
                    ),
                )
            )

        return self._result(placements, remaining)

    def _explain(
        self, task: _Task, factors: dict[str, float], *, guard_override: bool
    ) -> Explanation:
        if task.at_risk:
            reason = Reason.BEST_EFFORT
        elif guard_override:
            reason = Reason.DEADLINE_GUARD
        else:
            # Sorted first, so that equal contributions always resolve the same way.
            strongest = max(sorted(factors), key=lambda name: WEIGHTS[name] * factors[name])
            reason = _REASON_FOR_FACTOR[strongest]
        deadline = (
            None
            if task.real_deadline is None
            else self.timeline.origin + timedelta(minutes=task.real_deadline)
        )
        return Explanation(reason, factors, guard_override, deadline)

    def _result(self, placements: list[Placement], remaining: list[int]) -> PlanResult:
        at_risk = [AtRiskTask(tid, m, RiskReason.OVERDUE) for tid, m in self.overdue]
        unplaced: list[UnplacedTask] = []
        for task in self.tasks:
            minutes = remaining[task.index]
            if minutes == 0:
                continue
            if task.guarded:
                at_risk.append(AtRiskTask(task.id, minutes, RiskReason.INSUFFICIENT_TIME))
            else:
                unplaced.append(UnplacedTask(task.id, minutes))
        return PlanResult(
            placements=tuple(placements),
            at_risk=tuple(sorted(at_risk, key=lambda item: item.task_id)),
            unplaced=tuple(unplaced),
        )


def plan(request: PlanRequest) -> PlanResult:
    """Build a study plan. The same request always produces the same result."""
    return _Planner(request).run()


def plain_edf_late_minutes(request: PlanRequest) -> int:
    """Minutes that plain EDF finishes late on the same slots. The baseline the guard must match."""
    planner = _Planner(request)
    for task in planner.tasks:
        task.deadline = task.real_deadline
    planner._set_guard_order()  # noqa: SLF001
    return sum(minutes for _, minutes in planner._late_from_start())  # noqa: SLF001
