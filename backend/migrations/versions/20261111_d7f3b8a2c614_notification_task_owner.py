"""A notification's task must belong to the same student, as for every other table.

Revision ID: d7f3b8a2c614
Revises: c5e2a9d41b70
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d7f3b8a2c614"
down_revision: str | None = "c5e2a9d41b70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("fk_notifications_task_id_tasks", "notifications", type_="foreignkey")
    op.create_foreign_key(
        "fk_notifications_task_owner",
        "notifications",
        "tasks",
        ["task_id", "user_id"],
        ["id", "user_id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_notifications_task_owner", "notifications", type_="foreignkey")
    op.create_foreign_key(
        "fk_notifications_task_id_tasks",
        "notifications",
        "tasks",
        ["task_id"],
        ["id"],
        ondelete="CASCADE",
    )
