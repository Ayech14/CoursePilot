"""Store calendar links encrypted, with a keyed digest to spot duplicates.

Existing links are encrypted in place with the key from the environment (CALENDAR_LINK_KEY, or the
JWT secret outside production), so that key must be the one the app will run with.

Revision ID: e2a9c5f1d837
Revises: d7f3b8a2c614
"""

from collections.abc import Sequence
from urllib.parse import urlsplit

import sqlalchemy as sa
from alembic import op

from app.core.config import get_settings
from app.core.link_cipher import LinkCipher, master_key

revision: str = "e2a9c5f1d837"
down_revision: str | None = "d7f3b8a2c614"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

feeds = sa.table(
    "calendar_feeds",
    sa.column("id", sa.Uuid),
    sa.column("url", sa.Text),
    sa.column("url_ciphertext", sa.Text),
    sa.column("url_digest", sa.String),
    sa.column("url_host", sa.String),
)


def _cipher() -> LinkCipher:
    return LinkCipher(master_key(get_settings()))


def upgrade() -> None:
    op.add_column("calendar_feeds", sa.Column("url_ciphertext", sa.Text(), nullable=True))
    op.add_column("calendar_feeds", sa.Column("url_digest", sa.String(64), nullable=True))
    op.add_column("calendar_feeds", sa.Column("url_host", sa.String(255), nullable=True))

    connection = op.get_bind()
    cipher = _cipher()
    for feed_id, url in connection.execute(sa.select(feeds.c.id, feeds.c.url)).all():
        connection.execute(
            feeds.update()
            .where(feeds.c.id == feed_id)
            .values(
                url_ciphertext=cipher.encrypt(url),
                url_digest=cipher.digest(url),
                url_host=urlsplit(url).hostname or "",
            )
        )

    for name in ("url_ciphertext", "url_digest", "url_host"):
        op.alter_column("calendar_feeds", name, nullable=False)
    op.drop_constraint("uq_calendar_feeds_user_id_url", "calendar_feeds", type_="unique")
    op.drop_constraint(op.f("ck_calendar_feeds_url_length"), "calendar_feeds", type_="check")
    op.drop_column("calendar_feeds", "url")
    op.create_unique_constraint(
        "uq_calendar_feeds_user_id_url_digest", "calendar_feeds", ["user_id", "url_digest"]
    )


def downgrade() -> None:
    op.add_column("calendar_feeds", sa.Column("url", sa.Text(), nullable=True))
    connection = op.get_bind()
    cipher = _cipher()
    for feed_id, token in connection.execute(sa.select(feeds.c.id, feeds.c.url_ciphertext)).all():
        connection.execute(
            feeds.update().where(feeds.c.id == feed_id).values(url=cipher.decrypt(token))
        )
    op.alter_column("calendar_feeds", "url", nullable=False)
    op.drop_constraint("uq_calendar_feeds_user_id_url_digest", "calendar_feeds", type_="unique")
    for name in ("url_ciphertext", "url_digest", "url_host"):
        op.drop_column("calendar_feeds", name)
    op.create_unique_constraint("uq_calendar_feeds_user_id_url", "calendar_feeds", ["user_id", "url"])
    op.create_check_constraint(
        op.f("ck_calendar_feeds_url_length"), "calendar_feeds", "char_length(url) <= 2000"
    )
