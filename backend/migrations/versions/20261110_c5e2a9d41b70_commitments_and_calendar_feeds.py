"""Categories for busy time, and calendars connected by link.

Revision ID: c5e2a9d41b70
Revises: a4c1e7d2b903
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c5e2a9d41b70'
down_revision: str | None = 'a4c1e7d2b903'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


CATEGORIES = "'class', 'work', 'social', 'personal', 'other'"


def _add_category(table: str) -> None:
    # add_column does not create an Enum's CHECK constraint, so it is added explicitly.
    op.add_column(
        table, sa.Column("category", sa.String(length=32), server_default="other", nullable=False)
    )
    op.create_check_constraint(op.f(f"ck_{table}_block_category"), table, f"category IN ({CATEGORIES})")


def upgrade() -> None:
    op.create_table('calendar_feeds',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('url', sa.Text(), nullable=False),
    sa.Column('last_attempt_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('busy_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('char_length(url) <= 2000', name=op.f('ck_calendar_feeds_url_length')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_calendar_feeds_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_calendar_feeds')),
    sa.UniqueConstraint('user_id', 'url', name=op.f('uq_calendar_feeds_user_id_url'))
    )
    op.create_table('deadline_suggestions',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('feed_id', sa.Uuid(), nullable=False),
    sa.Column('external_uid', sa.String(length=500), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('due_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('course_id', sa.Uuid(), nullable=True),
    sa.Column('status', sa.Enum('pending', 'accepted', 'dismissed', name='suggestion_status', native_enum=False, create_constraint=True, length=32), server_default='pending', nullable=False),
    sa.Column('task_id', sa.Uuid(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['course_id'], ['courses.id'], name=op.f('fk_deadline_suggestions_course_id_courses'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['feed_id'], ['calendar_feeds.id'], name=op.f('fk_deadline_suggestions_feed_id_calendar_feeds'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], name=op.f('fk_deadline_suggestions_task_id_tasks'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_deadline_suggestions_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_deadline_suggestions')),
    sa.UniqueConstraint('feed_id', 'external_uid', name=op.f('uq_deadline_suggestions_feed_id_external_uid'))
    )
    op.create_index(op.f('ix_deadline_suggestions_user_id_status'), 'deadline_suggestions', ['user_id', 'status'], unique=False)
    _add_category('one_off_blocks')
    op.add_column('one_off_blocks', sa.Column('feed_id', sa.Uuid(), nullable=True))
    op.add_column('one_off_blocks', sa.Column('external_uid', sa.String(length=500), nullable=True))
    op.create_index(op.f('ix_one_off_blocks_feed_id'), 'one_off_blocks', ['feed_id'], unique=False)
    op.create_foreign_key(op.f('fk_one_off_blocks_feed_id_calendar_feeds'), 'one_off_blocks', 'calendar_feeds', ['feed_id'], ['id'], ondelete='CASCADE')
    op.create_check_constraint(op.f('ck_one_off_blocks_import_fields_together'), 'one_off_blocks', '(feed_id IS NULL) = (external_uid IS NULL)')
    _add_category('recurring_blocks')


def downgrade() -> None:
    op.drop_column('recurring_blocks', 'category')
    op.drop_constraint(op.f('ck_one_off_blocks_import_fields_together'), 'one_off_blocks', type_='check')
    op.drop_constraint(op.f('fk_one_off_blocks_feed_id_calendar_feeds'), 'one_off_blocks', type_='foreignkey')
    op.drop_index(op.f('ix_one_off_blocks_feed_id'), table_name='one_off_blocks')
    op.drop_column('one_off_blocks', 'external_uid')
    op.drop_column('one_off_blocks', 'feed_id')
    op.drop_column('one_off_blocks', 'category')
    op.drop_index(op.f('ix_deadline_suggestions_user_id_status'), table_name='deadline_suggestions')
    op.drop_table('deadline_suggestions')
    op.drop_table('calendar_feeds')
