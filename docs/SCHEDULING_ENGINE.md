# CoursePilot — Scheduling Engine Design

> **Status:** implemented through Milestone 4, except the constraint-optimization comparison in
> section 11, which is proposed for Milestone 7.

## 1. Interface

The engine is a pure function, in a package that imports nothing from the web or database layers.

```python
def plan(request: PlanRequest) -> PlanResult: ...
```

`PlanRequest` holds `now`, the user's time zone, the horizon, tasks, availability, blocks,
preferences and existing sessions. `PlanResult` holds placements, at-risk tasks and explanations.
The same input always gives the same output: no clock reads, no randomness, and every tie is broken
by a stable key. Determinism makes behavior testable and makes bug reports reproducible.

## 2. Why not simply earliest-deadline-first?

| Strategy | Strength | Weakness for students |
|----------|----------|-----------------------|
| Earliest deadline first (EDF) | Very strong at meeting deadlines | Crams; finishes one task before starting the next; no balance |
| As late as possible | Keeps early days open | No margin; one bad day causes a miss |
| Weighted score only | Natural balance | Can miss deadlines that EDF would have met |
| Constraint optimization (CP-SAT) | Near-optimal against an objective | Heavy dependency; harder to explain; needs a baseline to justify it |

The design combines the first and third: **a weighted score chooses what is good, and an EDF
simulation vetoes anything that would cost a deadline.** The result gets the balance of scoring with
a concrete guarantee taken from EDF (§6).

## 3. Pipeline

```text
1. Build timeline   availability − blocks − pinned sessions − breaks → candidate slots
2. Compute demand   remaining effort − minutes already held by kept sessions
3. Feasibility      EDF simulation → at-risk tasks, reported before anything is placed
4. Pacing           a soft study target per day, to spread work out
5. Guarded greedy   each slot, chronologically: best scoring choice that passes the guard
6. Explain          attach a structured reason to each placement
```

## 4. Timeline construction

For each **local date** in the horizon:

1. Expand the weekly windows to real instants in the user's time zone.
2. Subtract recurring blocks, one-off blocks and existing pinned sessions, with a break-sized
   margin around each pinned session.
3. Clip to `now`, rounded up to the next 5 minutes.
4. Cut what remains into **slots** of the preferred length, separated by the preferred break.
   Remainders shorter than the minimum session length are discarded.

The day's budget is `max_daily_minutes` minus pinned minutes on that date. Days are local dates, so a
session is attributed to the day the student experiences it.

**Daylight saving rules** (these get dedicated tests):

| Situation | Rule |
|-----------|------|
| Local time does not exist (spring forward) | Snap to the first valid instant after the gap |
| Local time occurs twice (fall back) | Use the first occurrence (`fold=0`) |
| 23- or 25-hour days | Handled naturally: all arithmetic is on UTC instants, per local date |

## 5. Selecting work

### Chunking
Work is cut into sessions no longer than the preferred length. If the final chunk would be below the
minimum, it takes minutes from the previous chunk. For example, 105 minutes with a preferred length
of 50 and a minimum of 25 becomes 50 + 30 + 25, rather than 50 + 50 + 5.

### Pacing
Without pacing, a greedy planner fills every early slot and the student has a brutal first week. Each
task instead has a linear pace, its remaining minutes divided by the study-available days before its
deadline. Their running total gives a **cumulative soft target** for each day. Once placed work reaches
that day's target, "leave this slot empty" becomes a legal choice. A cumulative target stops rounding
to whole sessions from drifting. Pacing never overrides the guard, so a tight deadline still fills the
day, and a slot is not left empty while at-risk work could use it.

### Score
For a task `t` at slot `s`, with each factor normalized to 0–1:

```text
score = 0.50 · urgency + 0.25 · priority + 0.15 · course_balance + 0.10 · variety
```

| Factor | Definition | Requirement met |
|--------|------------|-----------------|
| `urgency` | `remaining / capacity from s to the deadline` (critical ratio) | Deadlines, remaining work, time remaining |
| `priority` | User priority scaled to 0–1 | Priority |
| `course_balance` | Higher when this course has had less of the recent planned time | Course balance |
| `variety` | Lower if this task already has a session today | Realistic days |

Urgency uses *available study capacity*, not calendar days. Five days away with no free time is
genuinely more urgent than five days away with free evenings. Ties break on deadline, then task ID.
**The weights are reasoned starting values and have not been tuned against data.** Tuning them needs
plan-quality metrics across many workloads, which belongs with the M7 comparison.

## 6. The feasibility guard

The guard is the core idea of the engine.

Let `shortfall(state)` be the total minutes that would finish late if all remaining work were
scheduled with EDF over the remaining slots. For each slot:

```text
baseline = shortfall(after placing the EDF choice)
for candidate in candidates ordered by score (at most K):
    if shortfall(after placing candidate) <= baseline:
        place candidate; break
else:
    place the EDF choice
```

**The guarantee:** if plain EDF can meet every deadline on the available slots, the plan does too.
Every step either takes the EDF choice or is proven by simulation to be no worse. In an overloaded
week, every task not reported as at risk still meets its deadline.

**The limit of that guarantee.** On one machine with freely divisible work, EDF is provably optimal
(Jackson's and Horn's results). Here, slots are discrete and a short final chunk can waste the end of
a slot, so the problem has a bin-packing flavor, and EDF is an excellent heuristic rather than an
exact optimum. The claim is therefore "as good as EDF on the available slots". It does not claim to
find a plan whenever one exists. Quantifying that gap is the purpose of the M7 comparison.

**Cost.** One simulation is about `O(S log T)` for `S` slots and `T` tasks, and stops as soon as all
protected work is placed. With a candidate cap `K`, a full plan costs about `O(K · S² log T)` in the
worst case. Measured on an Apple Silicon laptop, 60 tasks took 0.26 s over a 28-day horizon and 0.48 s
over 120 days. `test_planning_time_stays_interactive` keeps this honest.

### Deadline buffer
Planning first uses `deadline − buffer` (12 hours by default), so work does not finish minutes before
it is due. A task that cannot meet its buffered deadline falls back to the real one, and tasks that
can keep their margin. Tasks that cannot be saved at all are identified first, so that one hopeless
task cannot cost every other task its margin.

### Overload
If work cannot fit, a Moore–Hodgson style pass runs. While EDF misses a deadline, the lowest-priority
task among those due by that deadline is marked **at risk** and removed from the guard. It still
receives any leftover slots. This stops one impossible task from dragging others past their
deadlines. The result reports each at-risk task and its shortfall in minutes.

A task whose deadline has already passed is not scheduled, because no session could satisfy it. It is
reported as overdue, and setting a new deadline brings it back into the plan.

Undated work and work due after the horizon can never be late within the plan. Whatever is not reached
is reported separately and is not treated as a problem.

## 7. Explanations

Each placement stores data, and the text is generated from it, so wording can change without
re-planning and the UI can show the numbers.

```json
{
  "primary_reason": "deadline_pressure",
  "factors": { "urgency": 0.82, "priority": 0.67, "course_balance": 0.40, "variety": 1.0 },
  "guard_override": false,
  "deadline_at": "2026-11-20T23:59:00Z"
}
```

Rendered as: *"Scheduled now because this assignment needs 82% of your remaining study time before
it is due."*

## 8. Adaptive rescheduling (M4)

The default mode is **repair**, not rebuild.

```text
1. Classify future sessions: locked / sticky / flexible.
2. Drop only what is invalid: its task is complete, it is past the task's deadline, its time left
   availability, it overlaps a block or kept session, or it breaks current session, break or
   daily-limit preferences.
3. Trim surplus: if a task has more planned time than remaining work, shorten or remove its latest
   sessions.
4. Treat what is left as fixed and plan only each task's deficit around it.
5. If that loses more work than a fresh plan would, release flexible sessions in growing batches,
   starting with the latest-deadline work before the failing deadline, until it stops being worse.
6. Release sticky sessions only as a last resort, and only if that saves more work. Each is flagged
   in the preview and can be declined individually. Locked sessions are never released.
7. Replan around the new sessions until nothing more fits, so a second update has nothing left to do.
8. Diff old vs new, pairing removals with new sessions of the same task as moves.
```

Work with no deadline inside the horizon is never "behind", so repair only tops it up to the share a
fresh plan would give it. Otherwise each update would find free time and add more sessions for it.

| Event | Effect |
|-------|--------|
| Missed session | Its minutes become deficit |
| Task overruns | `remaining` rises, creating deficit |
| Finished early | Surplus trimmed; slots free up |
| New task or exam | New demand; repair places it |
| Deadline changes | Sessions after the new deadline dropped; repair runs |
| Availability changes | Sessions outside the new windows dropped; repair runs |

**Regenerate** is the explicit alternative. It releases every flexible session and rebuilds, keeping
locked and sticky ones.

**Stability** is reported as the share of previously planned future sessions left unchanged. Tests
assert that small events cause small diffs.

Events do not need dedicated triggers. Because repair compares reality with the plan, one dry run
when the schedule is opened detects any of them and offers a suggestion. Nothing is applied unasked.

## 9. Manual control (M4)

A manual move or resize runs through a pure `check_placement` function.

| Result | Examples | Behavior |
|--------|----------|----------|
| **Hard conflict** | Overlaps another session; start in the past | Refused with `409` and alternatives |
| **Warning** | Outside availability; over daily limit; in a block; no break; past the deadline | Returned to the user, who can confirm |

**Alternatives** come from a pure `suggest_slots` function: free slots of the same duration, ranked
by closeness to the requested time, preferring the same day and before the deadline.

A moved or resized session gets `user_modified_at` and becomes sticky. A locked session that collides
with a new block is not moved. It is reported as a conflict for the user to resolve. Any minutes
added or removed by a resize are treated as deficit or surplus on the next repair.

## 10. Invariants to test (M3–M4)

Checked on hand-written scenarios and on randomly generated ones:

1. No two sessions overlap.
2. Every automatic session lies inside availability and outside all blocks.
3. No local date exceeds the daily maximum because of automatic sessions.
4. Breaks are respected between automatic sessions.
5. No automatic session ends after its task's deadline.
6. A task never receives more minutes than it has remaining.
7. Locked sessions are identical before and after any plan.
8. Identical input gives byte-identical output.
9. If plain EDF on the same slots meets every deadline, the plan does too.
10. All of the above across DST transitions in several time zones.
11. Repairing and rebuilding produce schedules that obey all of the above.
12. Locked sessions are never changed by repair or rebuild.
13. Repairing an already repaired schedule changes nothing.
14. Repair never loses more work to overload than a rebuild would.

The checker in `tests/unit/scheduler/support.py` is written independently of the engine and works
from wall-clock rules, so a time-handling bug in the engine cannot hide by agreeing with itself.

## 11. Should constraint optimization come later?

Possibly, but only with evidence. Google OR-Tools CP-SAT is free, runs locally and could encode this
problem naturally. Its objective could maximize deadlines met, then balance, then stability.

The costs are a large binary dependency, less predictable run times, and explanations that are harder
to derive from a solver's answer. M7 proposes to implement it behind the same `plan` interface and
**compare it with the baseline on generated workloads**. It would replace the baseline only if the
measured improvement justifies those costs. Either outcome makes a good engineering story.
