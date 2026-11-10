"""Message request/response schemas."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class MessageSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sender: str
    recipient: str
    subject: Optional[str]
    received_at: datetime
    expires_at: Optional[datetime]
    is_read: bool


class MessageDetail(MessageSummary):
    text_body: Optional[str]
    html_body_sanitized: Optional[str]


class MessageReadUpdate(BaseModel):
    is_read: bool = Field(...)
