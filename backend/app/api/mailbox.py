"""Mailbox API routes."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import create_access_token
from app.core.dependencies import get_current_mailbox
from app.schemas.mailbox import (
    MailboxCreate,
    MailboxBatchCreate,
    MailboxLogin,
    MailboxResponse,
    MailboxDetailResponse,
    TokenResponse,
    PasswordUpdate,
)
from app.schemas.batch import BatchDetailResponse
from app.services.mailbox_service import MailboxService
from app.models.mailbox import Mailbox

router = APIRouter(prefix="/mailboxes", tags=["mailboxes"])


@router.post("", response_model=MailboxResponse, status_code=status.HTTP_201_CREATED)
def create_mailbox(
    payload: MailboxCreate,
    db: Session = Depends(get_db),
):
    """Create a single mailbox."""
    service = MailboxService(db)

    try:
        mailbox = service.create_mailbox(payload.email_address, payload.password)
        return mailbox
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@router.post("/batch", response_model=BatchDetailResponse, status_code=status.HTTP_201_CREATED)
def create_batch(
    payload: MailboxBatchCreate,
    db: Session = Depends(get_db),
):
    """Create multiple mailboxes at once."""
    service = MailboxService(db)

    try:
        batch, mailboxes = service.create_batch(
            quantity=payload.quantity,
            password=payload.password,
            generation_type=payload.generation_type,
            prefix=payload.prefix,
            custom_addresses=payload.custom_addresses,
        )

        return BatchDetailResponse(
            id=batch.id,
            quantity=batch.quantity,
            generation_type=batch.generation_type.value,
            created_at=batch.created_at,
            mailbox_count=len(mailboxes),
            mailboxes=[m.email_address for m in mailboxes],
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@router.post("/login", response_model=TokenResponse)
def login_mailbox(
    payload: MailboxLogin,
    db: Session = Depends(get_db),
):
    """Authenticate a mailbox."""
    service = MailboxService(db)
    mailbox = service.authenticate_mailbox(payload.email, payload.password)

    if not mailbox:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token, expires_in = create_access_token(mailbox.email_address)

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
    )


@router.get("/me", response_model=MailboxDetailResponse)
def get_current_mailbox_info(
    mailbox: Mailbox = Depends(get_current_mailbox),
):
    """Get current mailbox information."""
    return mailbox


@router.patch("/me/password", response_model=MailboxDetailResponse)
def update_mailbox_password(
    payload: PasswordUpdate,
    mailbox: Mailbox = Depends(get_current_mailbox),
    db: Session = Depends(get_db),
):
    """Update mailbox password."""
    service = MailboxService(db)

    # Verify current password
    if not service.authenticate_mailbox(mailbox.email_address, payload.current_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )

    # Update password
    updated_mailbox = service.update_password(mailbox, payload.new_password)
    return updated_mailbox


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_mailbox(
    mailbox: Mailbox = Depends(get_current_mailbox),
    db: Session = Depends(get_db),
):
    """Delete current mailbox."""
    service = MailboxService(db)
    service.delete_mailbox(mailbox)
