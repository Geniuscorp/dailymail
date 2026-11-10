"""Admin request/response schemas."""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class AdminLogin(BaseModel):
    username: str = Field(..., min_length=1, max_length=150)
    password: str = Field(..., min_length=1)


class AdminDashboard(BaseModel):
    total_mailboxes: int
    active_mailboxes: int
    total_messages: int
    total_attachments: int
    storage_used_mb: float
    expiring_soon: int


class AdminMailbox(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email_address: str
    status: str
    batch_id: Optional[int] = None
    created_at: datetime
    message_count: int = 0


class AdminMailboxUpdate(BaseModel):
    status: Literal["active", "blocked", "deleted"]


class AdminMailboxPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[AdminMailbox]


class AdminBatch(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    quantity: int
    generation_type: str
    created_at: datetime
    mailbox_count: int = 0


class AdminBatchPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[AdminBatch]


class AdminPasswordReset(BaseModel):
    new_password: str = Field(..., min_length=8)


class AdminMessage(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    mailbox_id: int
    recipient: str
    sender: str
    subject: Optional[str] = None
    received_at: datetime
    expires_at: Optional[datetime] = None
    is_read: bool
    attachment_count: int


class AdminMessagePage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[AdminMessage]


class AdminAttachment(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    message_id: int
    original_filename: str
    mime_type: str
    file_size: int
    created_at: datetime


class AdminAttachmentPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[AdminAttachment]
