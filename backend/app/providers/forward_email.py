"""Inbound email provider for forwardemail.net.

Replaces the Cloudflare Email Worker: some senders' mail silently never
arrives at Cloudflare Email Routing at all (its built-in anti-spam filtering
drops it before it is even logged, with no bounce — see docs/ARCHITECTURE.md),
regardless of SPF/DKIM/DMARC being correct. forwardemail.net is a different
receiving mail server with its own IP reputation, and already delivers the
`mailparser`-parsed message as this provider's webhook JSON, so there is no
MIME parsing to do here (unlike a raw-MIME provider such as AWS SES would need).

Authenticity: the free plan has no HMAC signing key (that is a paid-plan
feature, "Webhook Signature Payload Verification Key"). Forward Email's own
docs recommend verifying instead via a reverse DNS lookup of the caller's IP,
which must resolve to mx1.forwardemail.net or mx2.forwardemail.net. This is
still sound: the lookup runs against the connection's real source IP, which
cannot be spoofed over TCP/TLS the way a header could be, even though the
webhook URL itself is only as secret as the DNS TXT record that configures it.
"""
import asyncio
import json
import logging
import socket
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.providers.base import InboundAttachment, InboundEmailProvider, InboundMessage, InvalidWebhookError

logger = logging.getLogger(__name__)

TRUSTED_SENDING_HOSTS = {"mx1.forwardemail.net", "mx2.forwardemail.net"}
REVERSE_DNS_TIMEOUT_SECONDS = 5
MAX_FIELD_LENGTH = 998
MAX_BODY_LENGTH = 2_000_000


def _text_field(value: Any) -> Optional[str]:
    """mailparser represents a genuinely absent text/html body as `False`,
    not `null` — handle both as "no body"."""
    if value is None or value is False:
        return None
    if not isinstance(value, str):
        raise InvalidWebhookError("Field must be a string")
    return value[:MAX_BODY_LENGTH]


def _address_of(field: Any) -> Optional[str]:
    """mailparser's address-header shape: {"value": [{"address": "...", ...}], ...}."""
    if not isinstance(field, dict):
        return None
    values = field.get("value")
    if not isinstance(values, list) or not values:
        return None
    first = values[0]
    if not isinstance(first, dict):
        return None
    address = first.get("address")
    return address if isinstance(address, str) else None


def _parse_attachments(value: Any) -> tuple[InboundAttachment, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise InvalidWebhookError("attachments must be a list")
    parsed = []
    for item in value:
        if not isinstance(item, dict):
            raise InvalidWebhookError("attachment must be an object")
        content = item.get("content")
        if not isinstance(content, dict) or not isinstance(content.get("data"), list):
            # An attachment mailparser itself couldn't buffer (rare) is
            # dropped rather than failing the whole message, same policy as
            # attachment_policy.py applies to a rejected one downstream.
            logger.info("forward_email: attachment without buffered content dropped")
            continue
        try:
            data = bytes(content["data"])
        except (TypeError, ValueError) as exc:
            raise InvalidWebhookError("attachment content is not a byte array") from exc
        filename = item.get("filename")
        content_type = item.get("contentType")
        parsed.append(
            InboundAttachment(
                filename=filename[:MAX_FIELD_LENGTH] if isinstance(filename, str) else None,
                declared_content_type=content_type[:MAX_FIELD_LENGTH] if isinstance(content_type, str) else None,
                data=data,
            )
        )
    return tuple(parsed)


def _parse_received_at(payload: dict) -> Optional[datetime]:
    session = payload.get("session")
    raw = session.get("arrivalDate") if isinstance(session, dict) else None
    if not isinstance(raw, str):
        raw = payload.get("date") if isinstance(payload.get("date"), str) else None
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class ForwardEmailProvider(InboundEmailProvider):
    async def verify(self, headers: dict[str, str], raw_body: bytes, client_ip: Optional[str] = None) -> None:
        if not client_ip:
            raise InvalidWebhookError("No client IP to verify")
        try:
            hostname, _aliases, _addrs = await asyncio.wait_for(
                asyncio.to_thread(socket.gethostbyaddr, client_ip),
                timeout=REVERSE_DNS_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            raise InvalidWebhookError("Reverse DNS lookup timed out") from exc
        except OSError as exc:
            raise InvalidWebhookError(f"Reverse DNS lookup failed for {client_ip}") from exc

        if hostname not in TRUSTED_SENDING_HOSTS:
            raise InvalidWebhookError(f"Untrusted sending host: {hostname!r}")

    def parse(self, raw_body: bytes) -> InboundMessage:
        try:
            payload = json.loads(raw_body)
        except (ValueError, UnicodeDecodeError) as exc:
            raise InvalidWebhookError("Body is not valid JSON") from exc

        if not isinstance(payload, dict):
            raise InvalidWebhookError("Body must be a JSON object")

        session = payload.get("session")
        session = session if isinstance(session, dict) else {}

        recipients = payload.get("recipients")
        if isinstance(recipients, list) and len(recipients) > 1:
            # One email addressed to more than one of our mailboxes at once
            # (e.g. cc'd across two aliases) arrives as a single grouped
            # webhook call. Only the envelope recipient for this delivery
            # is ingested; the rest are logged, not silently lost without a
            # trace, since this is rare enough not to warrant a provider
            # interface that returns more than one InboundMessage.
            logger.warning(
                "forward_email: delivery grouped %s recipients, only session.recipient is ingested",
                len(recipients),
            )

        recipient = session.get("recipient")
        if not isinstance(recipient, str) or not recipient:
            raise InvalidWebhookError("Missing session.recipient")

        sender = session.get("sender")
        if not isinstance(sender, str) or not sender:
            sender = _address_of(payload.get("from"))
        if not sender:
            raise InvalidWebhookError("Missing sender")

        message_id = payload.get("messageId")
        if not isinstance(message_id, str) or not message_id:
            # Forward Email's own docs note Message-ID isn't always present;
            # fall back the same way the old Worker did for malformed mail.
            message_id = f"<{uuid.uuid4()}@forwardemail.local>"

        subject = payload.get("subject")

        return InboundMessage(
            provider_message_id=message_id[:MAX_FIELD_LENGTH],
            sender=sender[:MAX_FIELD_LENGTH].lower(),
            recipient=recipient[:MAX_FIELD_LENGTH].lower(),
            subject=subject[:MAX_FIELD_LENGTH] if isinstance(subject, str) else None,
            text_body=_text_field(payload.get("text")),
            html_body=_text_field(payload.get("html")),
            received_at=_parse_received_at(payload),
            attachments=_parse_attachments(payload.get("attachments")),
        )
