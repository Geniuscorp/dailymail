"""Admin API: authentication, dashboard and management of mailboxes, batches, messages."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_admin
from app.core.rate_limit import rate_limited
from app.core.security import create_admin_token
from app.models.admin_user import AdminUser
from app.schemas.admin import (
    AdminAttachmentPage,
    AdminBatchPage,
    AdminDashboard,
    AdminLogin,
    AdminMailbox,
    AdminMailboxPage,
    AdminMailboxUpdate,
    AdminMessagePage,
    AdminPasswordReset,
)
from app.schemas.mailbox import TokenResponse
from app.services.admin_service import AdminService
from app.storage import StorageNotConfiguredError, get_object_storage
from app.storage.base import ObjectStorage, StorageError

router = APIRouter(prefix="/admin", tags=["admin"])


def _service(db: Session) -> AdminService:
    storage: Optional[ObjectStorage]
    try:
        storage = get_object_storage()
    except StorageNotConfiguredError:
        storage = None
    return AdminService(db, storage=storage)


def _not_found(what: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} not found")


def _storage_unavailable(exc: StorageError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Attachment storage unavailable",
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limited("admin-login", "rate_limit_login_per_minute"))],
)
def admin_login(payload: AdminLogin, db: Session = Depends(get_db)):
    """Authenticate an admin user and return an admin-scoped token."""
    service = _service(db)
    if not service.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin access is not configured",
        )

    admin = service.authenticate(payload.username, payload.password)
    if admin is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    token, expires_in = create_admin_token(admin.username)
    return TokenResponse(access_token=token, token_type="bearer", expires_in=expires_in)


@router.get("/dashboard", response_model=AdminDashboard)
def dashboard(admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    return AdminDashboard(**_service(db).dashboard())


@router.get("/mailboxes", response_model=AdminMailboxPage)
def list_mailboxes(
    search: Optional[str] = Query(None, max_length=254),
    status_filter: Optional[str] = Query(
        None, alias="status", pattern="^(active|blocked|deleted)$"
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    total, items = _service(db).list_mailboxes(search, status_filter, limit, offset)
    return AdminMailboxPage(total=total, limit=limit, offset=offset, items=items)


@router.patch("/mailboxes/{mailbox_id}", response_model=AdminMailbox)
def update_mailbox(
    mailbox_id: int,
    payload: AdminMailboxUpdate,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    service = _service(db)
    mailbox = service.get_mailbox(mailbox_id)
    if mailbox is None:
        raise _not_found("Mailbox")

    updated = service.set_mailbox_status(admin, mailbox, payload.status)
    return AdminMailbox.model_validate(updated).model_copy(
        update={"message_count": service.count_messages(updated.id)}
    )


@router.delete("/mailboxes/{mailbox_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mailbox(
    mailbox_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    service = _service(db)
    mailbox = service.get_mailbox(mailbox_id)
    if mailbox is None:
        raise _not_found("Mailbox")
    service.delete_mailbox(admin, mailbox)


@router.get("/batches", response_model=AdminBatchPage)
def list_batches(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    total, items = _service(db).list_batches(limit, offset)
    return AdminBatchPage(total=total, limit=limit, offset=offset, items=items)


@router.patch("/batches/{batch_id}/password", status_code=status.HTTP_204_NO_CONTENT)
def reset_batch_password(
    batch_id: int,
    payload: AdminPasswordReset,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    service = _service(db)
    batch = service.get_batch(batch_id)
    if batch is None:
        raise _not_found("Batch")
    service.reset_batch_password(admin, batch, payload.new_password)


@router.get("/messages", response_model=AdminMessagePage)
def list_messages(
    mailbox_id: Optional[int] = Query(None, ge=1),
    search: Optional[str] = Query(None, max_length=254),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    total, items = _service(db).list_messages(limit, offset, mailbox_id, search)
    return AdminMessagePage(total=total, limit=limit, offset=offset, items=items)


@router.delete("/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_message(
    message_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    service = _service(db)
    message = service.get_message(message_id)
    if message is None:
        raise _not_found("Message")
    try:
        service.delete_message(admin, message)
    except StorageError as exc:
        raise _storage_unavailable(exc) from exc


@router.get("/attachments", response_model=AdminAttachmentPage)
def list_attachments(
    message_id: Optional[int] = Query(None, ge=1),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    total, items = _service(db).list_attachments(limit, offset, message_id)
    return AdminAttachmentPage(total=total, limit=limit, offset=offset, items=items)


@router.delete("/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_attachment(
    attachment_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    service = _service(db)
    attachment = service.get_attachment(attachment_id)
    if attachment is None:
        raise _not_found("Attachment")
    try:
        service.delete_attachment(admin, attachment)
    except StorageError as exc:
        raise _storage_unavailable(exc) from exc
