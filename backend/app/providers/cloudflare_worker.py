"""Inbound email provider for the DailyMail Cloudflare Email Worker.

The Worker signs each delivery as HMAC-SHA256 over "<timestamp>.<raw body>"
using INBOUND_WEBHOOK_SECRET and sends the result in X-DailyMail-Signature.
"""
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.config import get_settings
from app.providers.base import InboundEmailProvider, InboundMessage, InvalidWebhookError

SIGNATURE_HEADER = "x-dailymail-signature"
TIMESTAMP_HEADER = "x-dailymail-timestamp"
MAX_FIELD_LENGTH = 998  # RFC 5322 line limit for header-like fields
MAX_BODY_LENGTH = 2_000_000


def _sign(secret: str, timestamp: str, raw_body: bytes) -> str:
    message = timestamp.encode() + b"." + raw_body
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def _optional_str(value: Any, limit: int) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidWebhookError("Field must be a string")
    return value[:limit]


def _required_str(value: Any, limit: int) -> str:
    text = _optional_str(value, limit)
    if not text:
        raise InvalidWebhookError("Required field missing")
    return text


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidWebhookError("received_at must be a string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InvalidWebhookError("received_at is not ISO 8601") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class CloudflareWorkerProvider(InboundEmailProvider):
    def __init__(self, secret: str, tolerance_seconds: int):
        if not secret:
            raise RuntimeError("INBOUND_WEBHOOK_SECRET is not configured")
        self._secret = secret
        self._tolerance = tolerance_seconds

    def verify(self, headers: dict[str, str], raw_body: bytes) -> None:
        timestamp = headers.get(TIMESTAMP_HEADER)
        signature = headers.get(SIGNATURE_HEADER)
        if not timestamp or not signature:
            raise InvalidWebhookError("Missing signature headers")

        try:
            sent_at = int(timestamp)
        except ValueError as exc:
            raise InvalidWebhookError("Invalid timestamp") from exc

        if abs(time.time() - sent_at) > self._tolerance:
            raise InvalidWebhookError("Timestamp outside tolerance")

        expected = _sign(self._secret, timestamp, raw_body)
        if not hmac.compare_digest(expected, signature):
            raise InvalidWebhookError("Signature mismatch")

    def parse(self, raw_body: bytes) -> InboundMessage:
        try:
            payload = json.loads(raw_body)
        except (ValueError, UnicodeDecodeError) as exc:
            raise InvalidWebhookError("Body is not valid JSON") from exc

        if not isinstance(payload, dict):
            raise InvalidWebhookError("Body must be a JSON object")

        text_body = _optional_str(payload.get("text"), MAX_BODY_LENGTH)
        html_body = _optional_str(payload.get("html"), MAX_BODY_LENGTH)

        return InboundMessage(
            provider_message_id=_required_str(payload.get("message_id"), MAX_FIELD_LENGTH),
            sender=_required_str(payload.get("sender"), MAX_FIELD_LENGTH).lower(),
            recipient=_required_str(payload.get("recipient"), MAX_FIELD_LENGTH).lower(),
            subject=_optional_str(payload.get("subject"), MAX_FIELD_LENGTH),
            text_body=text_body,
            html_body=html_body,
            received_at=_parse_timestamp(payload.get("received_at")),
        )


def build_inbound_provider() -> InboundEmailProvider:
    settings = get_settings()
    if settings.inbound_email_provider == "cloudflare_worker":
        return CloudflareWorkerProvider(
            secret=settings.inbound_webhook_secret,
            tolerance_seconds=settings.inbound_webhook_tolerance_seconds,
        )
    raise RuntimeError(f"Unsupported INBOUND_EMAIL_PROVIDER: {settings.inbound_email_provider!r}")
