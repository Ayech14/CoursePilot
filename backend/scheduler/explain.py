"""Turns a structured explanation into a sentence a student can read."""

from scheduler.models import Explanation, Reason, RepairReason, RiskReason
from scheduler.placement import ConflictKind, WarningKind


def describe(explanation: Explanation) -> str:
    return describe_parts(explanation.primary_reason, explanation.factors["urgency"])


def describe_parts(reason: Reason, urgency: float) -> str:
    """Build the sentence from stored values, so that saved plans can be re-worded later."""
    match reason:
        case Reason.DEADLINE_PRESSURE:
            share = round(urgency * 100)
            return f"Scheduled now because this needs about {share}% of your time before it is due."
        case Reason.HIGH_PRIORITY:
            return "You marked this as important, so it goes ahead of less important work."
        case Reason.COURSE_BALANCE:
            return "Placed here to keep your courses balanced over the week."
        case Reason.VARIETY:
            return "Placed here so that you are not repeating the same task all day."
        case Reason.DEADLINE_GUARD:
            return (
                "Moved ahead of other work because leaving it later would risk a missed deadline."
            )
        case Reason.BEST_EFFORT:
            return "This cannot be finished before its deadline, so this uses the time available."


def describe_risk(reason: RiskReason) -> str:
    match reason:
        case RiskReason.OVERDUE:
            return (
                "The deadline has passed, so nothing was scheduled. Update the deadline to plan it."
            )
        case RiskReason.INSUFFICIENT_TIME:
            return "There is not enough available study time before the deadline."


def describe_repair(reason: RepairReason) -> str:
    match reason:
        case RepairReason.TASK_FINISHED:
            return "This task no longer needs study time."
        case RepairReason.LESS_WORK_NEEDED:
            return "Less work remains on this task than was scheduled."
        case RepairReason.PAST_DEADLINE:
            return "This session would end after the task's deadline."
        case RepairReason.OUTSIDE_AVAILABILITY:
            return "This time is no longer in your weekly study hours."
        case RepairReason.TIME_BLOCKED:
            return "Something else now takes up this time."
        case RepairReason.DAILY_LIMIT:
            return "This day is over your daily study limit."
        case RepairReason.SCHEDULE_RULES:
            return "This no longer fits your session length or break preferences."
        case RepairReason.MAKING_ROOM:
            return "This time is needed so that a more urgent task can meet its deadline."
        case RepairReason.REBUILT:
            return "Replaced as part of rebuilding your schedule."


def describe_conflict(kind: ConflictKind) -> str:
    match kind:
        case ConflictKind.OVERLAP:
            return "This overlaps another study session."
        case ConflictKind.IN_PAST:
            return "This time has already passed."


def describe_warning(kind: WarningKind) -> str:
    match kind:
        case WarningKind.OUTSIDE_AVAILABILITY:
            return "This is outside your weekly study hours."
        case WarningKind.IN_BLOCK:
            return "This overlaps a commitment or time off."
        case WarningKind.NO_BREAK:
            return "This leaves less than your preferred break next to another session."
        case WarningKind.DAILY_LIMIT:
            return "This puts the day over your daily study limit."
        case WarningKind.PAST_DEADLINE:
            return "This ends after the task's deadline."
