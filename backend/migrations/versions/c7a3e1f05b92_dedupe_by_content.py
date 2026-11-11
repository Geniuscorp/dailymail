"""De-duplicate inbound mail by content, not by Message-ID

VFS Global (and other transactional senders) reuse the same Message-ID across
genuinely different emails, so keying de-duplication on it dropped every OTP
after the first. Switch to a content hash: the same email re-delivered by
Cloudflare is byte-identical and still collapses, while a new OTP (a different
code, hence different content) is always stored.

- provider_message_id loses its unique index, keeps a plain one for lookup;
- new content_hash column, unique per (mailbox_id, content_hash).

Existing rows keep content_hash NULL; NULLs do not collide, so they neither
conflict with the new index nor block any future delivery.

Revision ID: c7a3e1f05b92
Revises: b4f17c9d2e51
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c7a3e1f05b92"
down_revision: Union[str, None] = "b4f17c9d2e51"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Message-ID is no longer a uniqueness key.
    op.drop_index("ix_messages_provider_message_id", table_name="messages")
    op.create_index(
        "ix_messages_provider_message_id",
        "messages",
        ["provider_message_id"],
        unique=False,
    )
    op.add_column("messages", sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.create_index(
        "ix_messages_mailbox_content_hash",
        "messages",
        ["mailbox_id", "content_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_messages_mailbox_content_hash", table_name="messages")
    op.drop_column("messages", "content_hash")
    op.drop_index("ix_messages_provider_message_id", table_name="messages")
    op.create_index(
        "ix_messages_provider_message_id",
        "messages",
        ["mailbox_id", "provider_message_id"],
        unique=True,
    )
