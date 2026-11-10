"""Tie a task's remaining effort to its completion status.

Revision ID: a4c1e7d2b903
Revises: 2cafa212aedb
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a4c1e7d2b903"
down_revision: str | None = "2cafa212aedb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT = "ck_tasks_remaining_matches_status"


def upgrade() -> None:
    op.create_check_constraint(
        op.f(CONSTRAINT), "tasks", "(status = 'completed') = (remaining_minutes = 0)"
    )


def downgrade() -> None:
    op.drop_constraint(op.f(CONSTRAINT), "tasks", type_="check")
