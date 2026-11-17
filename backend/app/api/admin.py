"""Admin API: authentication, dashboard and management of mailboxes, batches, messages."""
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.dependencies import get_current_admin
from app.core.rate_limit import rate_limited
from app.core.security import create_admin_token
from app.models.admin_user import AdminUser
from app.schemas.admin import (
    AdminAffected,
    AdminAttachmentPage,
    AdminAuditPage,
    AdminBatchPage,
    AdminDashboard,
    AdminLogin,
    AdminMailbox,
    AdminMailboxBulkStatus,
    AdminMailboxDetail,
    AdminMailboxPage,
    AdminMailboxUpdate,
    AdminMaintenanceResult,
    AdminMessageDetail,
    AdminMessagePage,
    AdminOverview,
    AdminOwnPasswordChange,
    AdminPasswordReset,
    AdminSystem,
    AdminUserCreate,
    AdminUserInfo,
    AdminUserUpdate,
)
from app.schemas.mailbox import TokenResponse
from app.services.admin_metrics import build_overview, build_system_info
from app.services.admin_service import AdminConflictError, AdminRuleError, AdminService
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

    service.record_login(admin)
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


@router.get("/overview", response_model=AdminOverview)
def overview(
    days: int = Query(30, ge=7, le=90),
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return build_overview(db, days)


@router.get("/system", response_model=AdminSystem)
def system(
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return build_system_info(
        get_settings(),
        version=request.app.version,
        storage_configured=_service(db).storage is not None,
    )


@router.get("/audit-logs", response_model=AdminAuditPage)
def audit_logs(
    action: Optional[str] = Query(None, pattern=r"^[a-z._-]{1,40}$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    total, items = _service(db).list_audit(action, limit, offset)
    return AdminAuditPage(total=total, limit=limit, offset=offset, items=items)


@router.get("/mailboxes/export")
def export_mailboxes(
    search: Optional[str] = Query(None, max_length=254),
    status_filter: Optional[str] = Query(None, alias="status", pattern="^(active|blocked|deleted)$"),
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    body = _service(db).export_mailboxes_csv(search, status_filter)
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=mailboxes.csv", "Cache-Control": "no-store"},
    )


@router.post("/mailboxes/bulk-status", response_model=AdminAffected)
def bulk_mailbox_status(
    payload: AdminMailboxBulkStatus,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return AdminAffected(affected=_service(db).bulk_set_mailbox_status(admin, payload.ids, payload.status))


@router.get("/mailboxes/{mailbox_id}", response_model=AdminMailboxDetail)
def mailbox_detail(
    mailbox_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    service = _service(db)
    mailbox = service.get_mailbox(mailbox_id)
    if mailbox is None:
        raise _not_found("Mailbox")
    return service.mailbox_detail(mailbox)


@router.post("/mailboxes/{mailbox_id}/password", status_code=status.HTTP_204_NO_CONTENT)
def reset_mailbox_password(
    mailbox_id: int,
    payload: AdminPasswordReset,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    service = _service(db)
    mailbox = service.get_mailbox(mailbox_id)
    if mailbox is None:
        raise _not_found("Mailbox")
    service.reset_mailbox_password(admin, mailbox, payload.new_password)


@router.delete("/mailboxes/{mailbox_id}/sessions", response_model=AdminAffected)
def revoke_mailbox_sessions(
    mailbox_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    service = _service(db)
    mailbox = service.get_mailbox(mailbox_id)
    if mailbox is None:
        raise _not_found("Mailbox")
    return AdminAffected(affected=service.revoke_mailbox_sessions(admin, mailbox))


@router.delete("/mailboxes/{mailbox_id}/messages", response_model=AdminAffected)
def clear_mailbox_messages(
    mailbox_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    service = _service(db)
    mailbox = service.get_mailbox(mailbox_id)
    if mailbox is None:
        raise _not_found("Mailbox")
    try:
        return AdminAffected(affected=service.clear_mailbox_messages(admin, mailbox))
    except StorageError as exc:
        raise _storage_unavailable(exc) from exc


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
    unread: Optional[bool] = Query(None),
    has_attachments: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    total, items = _service(db).list_messages(
        limit, offset, mailbox_id, search, unread=unread, has_attachments=has_attachments
    )
    return AdminMessagePage(total=total, limit=limit, offset=offset, items=items)


@router.get("/messages/{message_id}", response_model=AdminMessageDetail)
def message_detail(
    message_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    service = _service(db)
    message = service.get_message(message_id)
    if message is None:
        raise _not_found("Message")
    return service.message_detail(message)


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
    search: Optional[str] = Query(None, max_length=254),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    total, items = _service(db).list_attachments(limit, offset, message_id, search)
    return AdminAttachmentPage(total=total, limit=limit, offset=offset, items=items)


@router.get("/attachments/{attachment_id}/download")
def download_attachment(
    attachment_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    service = _service(db)
    attachment = service.get_attachment(attachment_id)
    if attachment is None:
        raise _not_found("Attachment")
    db.close()
    try:
        data = service.read_attachment(attachment)
    except StorageError as exc:
        raise _storage_unavailable(exc) from exc
    return Response(
        content=data,
        media_type=attachment.mime_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(attachment.original_filename)}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
            "Content-Length": str(len(data)),
        },
    )


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


# --- Administrators and maintenance -------------------------------------------


@router.get("/me", response_model=AdminUserInfo)
def me(admin: AdminUser = Depends(get_current_admin)):
    return admin


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
def change_own_password(
    payload: AdminOwnPasswordChange,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    if not _service(db).change_own_password(admin, payload.current_password, payload.new_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")


@router.get("/users", response_model=list[AdminUserInfo])
def list_admins(admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    return _service(db).list_admins()


@router.post("/users", response_model=AdminUserInfo, status_code=status.HTTP_201_CREATED)
def create_admin(
    payload: AdminUserCreate,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    try:
        return _service(db).create_admin(admin, payload.username, payload.password)
    except AdminConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.patch("/users/{admin_id}", response_model=AdminUserInfo)
def update_admin(
    admin_id: int,
    payload: AdminUserUpdate,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    service = _service(db)
    target = service.get_admin(admin_id)
    if target is None:
        raise _not_found("Admin")
    try:
        return service.set_admin_status(admin, target, payload.status)
    except AdminRuleError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/maintenance/purge-expired", response_model=AdminMaintenanceResult)
def purge_expired(admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    try:
        return AdminMaintenanceResult(affected=_service(db).purge_expired_messages(admin))
    except StorageError as exc:
        raise _storage_unavailable(exc) from exc


@router.post("/maintenance/purge-sessions", response_model=AdminMaintenanceResult)
def purge_sessions(admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    return AdminMaintenanceResult(affected=_service(db).purge_expired_sessions(admin))
