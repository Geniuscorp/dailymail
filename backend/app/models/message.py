"""Message model."""
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Boolean, Text, Index
from sqlalchemy.orm import relationship
from datetime import datetime

from app.models.base import Base


class Message(Base):
    __tablename__ = "messages"

    # A Message-ID is only unique per sender, and the same one legitimately
    # appears when a message is delivered to several recipients. A global
    # unique index let one sender that reuses its Message-ID (common in
    # templated transactional mail) block that mail for every mailbox in the
    # service: the first delivery was stored and every later one was discarded
    # as a duplicate. De-duplication belongs per mailbox.
    __table_args__ = (
        Index(
            "ix_messages_provider_message_id",
            "mailbox_id",
            "provider_message_id",
            unique=True,
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    mailbox_id = Column(Integer, ForeignKey("mailboxes.id"), nullable=False, index=True)
    provider_message_id = Column(String, nullable=True)
    sender = Column(String, nullable=False)
    recipient = Column(String, nullable=False)
    subject = Column(String, nullable=True)
    text_body = Column(Text, nullable=True)
    html_body_sanitized = Column(Text, nullable=True)
    received_at = Column(DateTime, default=datetime.utcnow, index=True)
    expires_at = Column(DateTime, nullable=True, index=True)
    is_read = Column(Boolean, default=False)

    # Relationships
    mailbox = relationship("Mailbox", back_populates="messages")
    attachments = relationship("Attachment", back_populates="message", cascade="all, delete-orphan")

    @property
    def attachment_count(self) -> int:
        return len(self.attachments)
