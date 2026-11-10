"""Inbound email webhook routes (called by the Cloudflare Email Worker)."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.providers.base import InvalidWebhookError
from app.providers.cloudflare_worker import build_inbound_provider
from app.services.message_service import MessageService

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/inbound-email", status_code=status.HTTP_202_ACCEPTED)
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
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Inbound email not configured") from exc

    headers = {key.lower(): value for key, value in request.headers.items()}
    try:
        provider.verify(headers, raw_body)
        inbound = provider.parse(raw_body)
    except InvalidWebhookError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Rejected webhook delivery") from exc

    result = MessageService(db).ingest(inbound)
    return {"status": result.value}
