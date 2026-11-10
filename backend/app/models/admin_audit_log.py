"""Admin audit log model."""
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from datetime import datetime

from app.models.base import Base


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(Integer, ForeignKey("admin_users.id"), nullable=False, index=True)
    action = Column(String, nullable=False)
    target_type = Column(String, nullable=False)
    target_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
