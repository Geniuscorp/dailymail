"""Message model."""
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.orm import relationship
from datetime import datetime

from app.models.base import Base


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    mailbox_id = Column(Integer, ForeignKey("mailboxes.id"), nullable=False, index=True)
    provider_message_id = Column(String, unique=True, index=True, nullable=True)
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
