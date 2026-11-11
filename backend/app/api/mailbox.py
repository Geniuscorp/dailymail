"""Mailbox API routes."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import rate_limited
from app.core.dependencies import get_current_mailbox, get_current_mailbox_session, require_creation_secret
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
from app.services.mailbox_service import MailboxConflictError, MailboxService, MailboxValidationError
from app.models.mailbox import Mailbox
from app.models.mailbox_session import MailboxSession

router = APIRouter(prefix="/mailboxes", tags=["mailboxes"])


@router.post(
    "",
    response_model=MailboxResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(rate_limited("mailbox-create", "rate_limit_create_per_minute")),
        Depends(require_creation_secret),
    ],
)
def create_mailbox(
    payload: MailboxCreate,
    db: Session = Depends(get_db),
):
    """Create a single mailbox."""
    service = MailboxService(db)

    try:
        mailbox = service.create_mailbox(payload.email_address, payload.password)
        return mailbox
    except MailboxValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except MailboxConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@router.post(
    "/batch",
    response_model=BatchDetailResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(rate_limited("mailbox-create", "rate_limit_create_per_minute")),
        Depends(require_creation_secret),
    ],
)
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
    except MailboxValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except MailboxConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limited("mailbox-login", "rate_limit_login_per_minute"))],
)
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

    # A token response, a persistent session: the frontend keeps it in
    # localStorage and never asks for the password again until it logs out or
    # every session is revoked (e.g. a password change elsewhere).
    service = MailboxService(db)
    token, expires_in = service.create_session(mailbox)

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout_mailbox(
    session: MailboxSession = Depends(get_current_mailbox_session),
    db: Session = Depends(get_db),
):
    """Revoke the current session only; other devices stay signed in."""
    MailboxService(db).revoke_session(session)


@router.get("/me", response_model=MailboxDetailResponse)
def get_current_mailbox_info(
    mailbox: Mailbox = Depends(get_current_mailbox),
):
    """Get current mailbox information."""
    return mailbox


@router.patch("/me/password", response_model=MailboxDetailResponse)
def update_mailbox_password(
    payload: PasswordUpdate,
    mailbox_session: MailboxSession = Depends(get_current_mailbox_session),
    db: Session = Depends(get_db),
):
    """Update mailbox password."""
    mailbox = mailbox_session.mailbox
    service = MailboxService(db)

    # Verify current password
    if not service.authenticate_mailbox(mailbox.email_address, payload.current_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )

    # Update password; every other session is signed out, this one is kept.
    updated_mailbox = service.update_password(mailbox, payload.new_password, keep_session_id=mailbox_session.id)
    return updated_mailbox


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_mailbox(
    mailbox: Mailbox = Depends(get_current_mailbox),
    db: Session = Depends(get_db),
):
    """Delete current mailbox."""
    service = MailboxService(db)
    service.delete_mailbox(mailbox)
