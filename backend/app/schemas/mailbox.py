"""Mailbox request/response schemas."""
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional


class MailboxCreate(BaseModel):
    """Create a single mailbox."""
    email_address: EmailStr = Field(..., description="Email address for the mailbox")
    password: str = Field(..., min_length=8, description="Password (min 8 characters)")


class MailboxBatchCreate(BaseModel):
    """Create multiple mailboxes at once."""
    quantity: int = Field(1, ge=1, le=100, description="Number of mailboxes to create")
    password: str = Field(..., min_length=8, description="Common password for all mailboxes")
    generation_type: str = Field("random", pattern="^(random|custom)$")
    prefix: Optional[str] = Field(None, description="Prefix for custom generation")
    custom_addresses: Optional[list[str]] = Field(None, description="Custom email addresses (for custom generation)")


class MailboxLogin(BaseModel):
    """Login to a mailbox."""
    email: EmailStr
    password: str


class MailboxResponse(BaseModel):
    """Mailbox response."""
    id: int
    email_address: str
    status: str
    created_at: datetime
    expires_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class MailboxDetailResponse(MailboxResponse):
    """Detailed mailbox response."""
    batch_id: Optional[int] = None


class TokenResponse(BaseModel):
    """Authentication token response."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 86400


class PasswordUpdate(BaseModel):
    """Update mailbox password."""
    current_password: str
    new_password: str = Field(..., min_length=8)
