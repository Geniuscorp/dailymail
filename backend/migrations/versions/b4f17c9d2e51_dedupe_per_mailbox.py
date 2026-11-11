"""Scope inbound de-duplication to the mailbox

A Message-ID is only unique per sender, and the same one legitimately appears
when a message is delivered to several recipients. The global unique index let
one sender that reuses its Message-ID block that mail for every mailbox in the
service: the first delivery was stored and every later one was answered 202
"duplicate" and silently discarded.

Revision ID: b4f17c9d2e51
Revises: e6bbf854ee0f
"""
from typing import Sequence, Union

from alembic import op

revision: str = "b4f17c9d2e51"
down_revision: Union[str, None] = "e6bbf854ee0f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_messages_provider_message_id", table_name="messages")
    op.create_index(
        "ix_messages_provider_message_id",
        "messages",
        ["mailbox_id", "provider_message_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_messages_provider_message_id", table_name="messages")
    op.create_index(
        "ix_messages_provider_message_id",
        "messages",
        ["provider_message_id"],
        unique=True,
    )
