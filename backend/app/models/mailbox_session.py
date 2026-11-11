"""Mailbox session model.

A mailbox session is an opaque, DB-backed credential: unlike a stateless JWT it
can be looked up, inspected and revoked (logout, password change) without
waiting for an expiry. Only the SHA-256 hash of the token is stored, the same
way a password reset or "remember me" token is usually kept.
"""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from datetime import datetime

from app.models.base import Base


class MailboxSession(Base):
    __tablename__ = "mailbox_sessions"

    id = Column(Integer, primary_key=True, index=True)
    mailbox_id = Column(Integer, ForeignKey("mailboxes.id"), nullable=False, index=True)
    token_hash = Column(String, unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False, index=True)

    mailbox = relationship("Mailbox", back_populates="sessions")
