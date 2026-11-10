"""Batch model."""
from sqlalchemy import Column, String, Integer, DateTime, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
from enum import Enum

from app.models.base import Base


class BatchGenerationType(str, Enum):
    RANDOM = "random"
    CUSTOM = "custom"


class Batch(Base):
    __tablename__ = "batches"

    id = Column(Integer, primary_key=True, index=True)
    quantity = Column(Integer, nullable=False)
    generation_type = Column(SQLEnum(BatchGenerationType), default=BatchGenerationType.RANDOM)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    mailboxes = relationship("Mailbox", back_populates="batch", cascade="all, delete-orphan")
