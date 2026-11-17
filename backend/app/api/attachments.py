"""Attachment routes (authenticated; bytes are served by the backend, never from R2 directly)."""
import logging
import time
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_mailbox
from app.models.mailbox import Mailbox
from app.schemas.message import AttachmentSummary
from app.services.attachment_policy import ALLOWED_FORMATS, extension_of
from app.services.message_service import MessageService
from app.storage import StorageNotConfiguredError, get_object_storage
from app.storage.base import StorageError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/attachments", tags=["attachments"])

# Formats a browser can display safely; everything else is download-only.
INLINE_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "gif"}
# Applied to inline responses so an embedded document cannot reach the app origin.
INLINE_CSP = "sandbox; default-src 'none'"


def _get_service(db: Session) -> MessageService:
    try:
        storage = get_object_storage()
    except StorageNotConfiguredError:
        storage = None
    return MessageService(db, storage=storage)


def _content_disposition(filename: str, inline: bool) -> str:
    kind = "inline" if inline else "attachment"
    return f"{kind}; filename*=UTF-8''{quote(filename)}"


@router.get("/{attachment_id}", response_model=AttachmentSummary)
def get_attachment(
    attachment_id: int,
    mailbox: Mailbox = Depends(get_current_mailbox),
    db: Session = Depends(get_db),
):
    attachment = _get_service(db).get_attachment_for_mailbox(mailbox, attachment_id)
    if attachment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    return attachment


@router.get("/{attachment_id}/download")
def download_attachment(
    attachment_id: int,
    request: Request,
    inline: bool = Query(False),
    mailbox: Mailbox = Depends(get_current_mailbox),
    db: Session = Depends(get_db),
):
    service = _get_service(db)
    attachment = service.get_attachment_for_mailbox(mailbox, attachment_id)
    if attachment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")

    # The attachment row is loaded; give the connection back to the pool
    # before the (possibly slow) object-storage transfer.
    db.close()
    started = time.monotonic()
    try:
        data = service.read_attachment(attachment)
    except StorageError as exc:
        logger.warning(
            "attachment %s read failed after %.0f ms client=%s",
            attachment_id,
            (time.monotonic() - started) * 1000,
            request.client.host if request.client else None,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Attachment storage unavailable"
        ) from exc

    logger.info(
        "attachment %s read %d bytes in %.0f ms client=%s",
        attachment_id,
        len(data),
        (time.monotonic() - started) * 1000,
        request.client.host if request.client else None,
    )
    extension = extension_of(attachment.original_filename)
    display_inline = inline and extension in INLINE_EXTENSIONS and extension in ALLOWED_FORMATS
    headers = {
        "Content-Disposition": _content_disposition(attachment.original_filename, display_inline),
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
        "Content-Length": str(len(data)),
    }
    if display_inline:
        headers["Content-Security-Policy"] = INLINE_CSP
    return Response(content=data, media_type=attachment.mime_type, headers=headers)
