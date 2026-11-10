"""Batch request/response schemas."""
from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class BatchResponse(BaseModel):
    """Batch response."""
    id: int
    quantity: int
    generation_type: str
    created_at: datetime
    mailbox_count: Optional[int] = 0

    class Config:
        from_attributes = True


class BatchDetailResponse(BatchResponse):
    """Detailed batch response with mailboxes."""
    mailboxes: list[str] = []
