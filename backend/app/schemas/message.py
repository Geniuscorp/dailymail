"""Message request/response schemas."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AttachmentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_filename: str
    mime_type: str
    file_size: int
    created_at: datetime


class MessageSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sender: str
    recipient: str
    subject: Optional[str]
    received_at: datetime
    expires_at: Optional[datetime]
    is_read: bool
    attachment_count: int


class MessageDetail(MessageSummary):
    text_body: Optional[str]
    html_body_sanitized: Optional[str]
    attachments: list[AttachmentSummary]


class MessageReadUpdate(BaseModel):
    is_read: bool = Field(...)
