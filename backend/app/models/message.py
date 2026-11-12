"""Message model."""
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Boolean, Text, Index
from sqlalchemy.orm import relationship
from datetime import datetime

from app.models.base import Base


class Message(Base):
    __tablename__ = "messages"

    # De-duplication keys on the message CONTENT, not the Message-ID.
    #
    # The only legitimate duplicate is Cloudflare re-delivering the *same*
    # email after a failed attempt; those re-deliveries are byte-for-byte
    # identical, so a content hash catches them. Keying on the Message-ID
    # instead was wrong: a sender that reuses its Message-ID across genuinely
    # different emails (VFS Global does this for every OTP) made each new
    # message look like a repeat of the first, so only the first was ever
    # stored and every later OTP — a different code, a real new email — was
    # silently dropped. Hashing the content keeps every distinct message
    # (different code -> different hash) while still collapsing true repeats.
    #
    # provider_message_id is kept for reference/debugging only, non-unique.
    __table_args__ = (
        Index("ix_messages_provider_message_id", "provider_message_id"),
        Index(
            "ix_messages_mailbox_content_hash",
            "mailbox_id",
            "content_hash",
            unique=True,
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    mailbox_id = Column(Integer, ForeignKey("mailboxes.id"), nullable=False, index=True)
    provider_message_id = Column(String, nullable=True)
    # sha256 of the delivered content (recipient, sender, subject, bodies).
    # Nullable so rows written before this column existed keep working; NULLs
    # do not collide in the unique index, so legacy rows never block anything.
    content_hash = Column(String(64), nullable=True)
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
