"""Turns a structured explanation into a sentence a student can read."""

from scheduler.models import Explanation, Reason, RiskReason


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
