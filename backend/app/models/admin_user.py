"""Admin user model."""
from sqlalchemy import Column, String, Integer, DateTime, Enum as SQLEnum
from datetime import datetime
from enum import Enum

from app.models.base import Base


class AdminUserStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class AdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    status = Column(SQLEnum(AdminUserStatus), default=AdminUserStatus.ACTIVE)
    created_at = Column(DateTime, default=datetime.utcnow)
