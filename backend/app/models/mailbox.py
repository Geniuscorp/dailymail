"""Mailbox model."""
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
from enum import Enum

from app.models.base import Base


class MailboxStatus(str, Enum):
    ACTIVE = "active"
    BLOCKED = "blocked"
    DELETED = "deleted"


class Mailbox(Base):
    __tablename__ = "mailboxes"

    id = Column(Integer, primary_key=True, index=True)
    email_address = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=True, index=True)
    status = Column(SQLEnum(MailboxStatus), default=MailboxStatus.ACTIVE, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    # Unused: mailboxes never expire, only their messages do. The column is kept
    # for databases created before that rule was settled, and is always NULL for
    # new mailboxes.
    expires_at = Column(DateTime, nullable=True, index=True)

    # Relationships
    batch = relationship("Batch", back_populates="mailboxes")
    messages = relationship("Message", back_populates="mailbox", cascade="all, delete-orphan")
    sessions = relationship("MailboxSession", back_populates="mailbox", cascade="all, delete-orphan")
