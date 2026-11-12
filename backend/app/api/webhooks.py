"""Inbound email webhook routes (called by the configured INBOUND_EMAIL_PROVIDER)."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import rate_limited
from app.providers import build_inbound_provider
from app.providers.base import InvalidWebhookError
from app.services.message_service import MessageService
from app.storage import StorageNotConfiguredError, get_object_storage
from app.storage.base import ObjectStorage

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _optional_storage() -> ObjectStorage | None:
    try:
        return get_object_storage()
    except StorageNotConfiguredError:
        return None


@router.post(
    "/inbound-email",
    status_code=status.HTTP_202_ACCEPTED,
    # Signature verification only happens after the full body is read, so an
    # unauthenticated caller could otherwise repeat large requests for free.
    dependencies=[Depends(rate_limited("inbound-webhook", "rate_limit_webhook_per_minute"))],
)
async def inbound_email(request: Request, db: Session = Depends(get_db)):
    settings = get_settings()
    max_bytes = settings.max_inbound_payload_mb * 1024 * 1024

    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > max_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Payload too large")

    raw_body = await request.body()
    if len(raw_body) > max_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Payload too large")

    try:
        provider = build_inbound_provider()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Inbound email not configured"
        ) from exc

    headers = {key.lower(): value for key, value in request.headers.items()}
    client_ip = request.client.host if request.client else None
    try:
        await provider.verify(headers, raw_body, client_ip=client_ip)
        inbound = provider.parse(raw_body)
    except InvalidWebhookError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Rejected webhook delivery") from exc

    # ingest() never fails a delivery over attachments: a storage outage or
    # missing R2 credentials drops just the attachment(s) it couldn't store,
    # not the message's subject and body.
    result = MessageService(db, storage=_optional_storage()).ingest(inbound)
    return {"status": result.value}
