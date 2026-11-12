"""A daily study goal, and sessions the student started on the spot.

The goal is the student's own target and does not feed the scheduler. ``unplanned`` marks a
session created by "Start timer" rather than by planning, so discarding it removes it instead of
leaving a planned session behind in the past.

Revision ID: f4b1d6e8a903
Revises: e2a9c5f1d837
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f4b1d6e8a903"
down_revision: str | None = "e2a9c5f1d837"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("study_preferences", sa.Column("daily_goal_minutes", sa.Integer(), nullable=True))
    op.create_check_constraint(
        op.f("ck_study_preferences_goal_range"),
        "study_preferences",
        "daily_goal_minutes IS NULL OR daily_goal_minutes BETWEEN 15 AND 720",
    )
    op.add_column(
        "study_sessions",
        sa.Column("unplanned", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("study_sessions", "unplanned")
    op.drop_constraint(
        op.f("ck_study_preferences_goal_range"), "study_preferences", type_="check"
    )
    op.drop_column("study_preferences", "daily_goal_minutes")
