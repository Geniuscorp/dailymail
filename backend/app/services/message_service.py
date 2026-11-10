"""Inbound message storage and mailbox message access."""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

import nh3
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.attachment import Attachment
from app.models.mailbox import Mailbox, MailboxStatus
from app.models.message import Message
from app.providers.base import InboundMessage
from app.services.attachment_policy import AttachmentRejectedError, validate_attachment
from app.storage.base import ObjectStorage, StorageError

logger = logging.getLogger(__name__)

HTML_ALLOWED_TAGS = {
    "a", "abbr", "b", "blockquote", "br", "code", "div", "em", "h1", "h2", "h3",
    "h4", "h5", "h6", "hr", "i", "li", "ol", "p", "pre", "small", "span",
    "strong", "table", "tbody", "td", "th", "thead", "tr", "u", "ul",
}


class IngestResult(str, Enum):
    STORED = "stored"
    DUPLICATE = "duplicate"
    IGNORED = "ignored"


def _not_expired(now: Optional[datetime] = None):
    """Rows whose retention window is still open (NULL expiry never expires)."""
    reference = now or datetime.now(timezone.utc)
    cutoff = reference.astimezone(timezone.utc).replace(tzinfo=None)
    return or_(Message.expires_at.is_(None), Message.expires_at > cutoff)


def sanitize_html(html: Optional[str]) -> Optional[str]:
    if not html:
        return None
    return nh3.clean(
        html,
        tags=HTML_ALLOWED_TAGS,
        link_rel="noopener noreferrer nofollow",
        url_schemes={"http", "https", "mailto"},
    )


class MessageService:
    def __init__(self, db: Session, storage: Optional[ObjectStorage] = None):
        self.db = db
        self.storage = storage
        self.settings = get_settings()

    def ingest(self, inbound: InboundMessage) -> IngestResult:
        mailbox = (
            self.db.query(Mailbox)
            .filter(
                Mailbox.email_address == inbound.recipient,
                Mailbox.status == MailboxStatus.ACTIVE,
            )
            .first()
        )
        if mailbox is None:
            return IngestResult.IGNORED

        if self._already_stored(inbound.provider_message_id):
            return IngestResult.DUPLICATE

        received_at = inbound.received_at or datetime.now(timezone.utc)
        received_at = received_at.astimezone(timezone.utc).replace(tzinfo=None)
        expires_at = received_at + timedelta(days=self.settings.email_retention_days)

        message = Message(
            mailbox_id=mailbox.id,
            provider_message_id=inbound.provider_message_id,
            sender=inbound.sender,
            recipient=inbound.recipient,
            subject=inbound.subject,
            text_body=inbound.text_body,
            html_body_sanitized=sanitize_html(inbound.html_body),
            received_at=received_at,
            expires_at=expires_at,
            is_read=False,
        )

        stored_keys = self._store_attachments(message, inbound)
        self.db.add(message)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            self._remove_objects(stored_keys)
            return IngestResult.DUPLICATE
        except Exception:
            self.db.rollback()
            self._remove_objects(stored_keys)
            raise
        return IngestResult.STORED

    def _store_attachments(self, message: Message, inbound: InboundMessage) -> list[str]:
        candidates = inbound.attachments[: self.settings.max_attachments_per_message]
        if len(inbound.attachments) > len(candidates):
            logger.info("attachments beyond per-message limit were dropped")
        max_bytes = self.settings.max_attachment_size_mb * 1024 * 1024

        keys: list[str] = []
        for candidate in candidates:
            try:
                accepted = validate_attachment(candidate.filename, candidate.data, max_bytes)
            except AttachmentRejectedError as exc:
                logger.info("attachment dropped: %s", exc)
                continue

            if self.storage is None:
                raise StorageError("attachment storage is not available")
            key = f"{uuid.uuid4().hex}.{accepted.extension}"
            try:
                self.storage.put(key, accepted.data, accepted.mime_type)
            except StorageError:
                self._remove_objects(keys)
                raise
            keys.append(key)
            message.attachments.append(
                Attachment(
                    original_filename=accepted.original_filename,
                    storage_key=key,
                    mime_type=accepted.mime_type,
                    file_size=len(accepted.data),
                )
            )
        return keys

    def _remove_objects(self, keys: list[str]) -> None:
        if self.storage is None:
            return
        for key in keys:
            try:
                self.storage.delete(key)
            except StorageError:
                logger.warning("orphaned attachment object could not be removed")

    def _already_stored(self, provider_message_id: str) -> bool:
        return (
            self.db.query(Message.id)
            .filter(Message.provider_message_id == provider_message_id)
            .first()
            is not None
        )

    def list_for_mailbox(self, mailbox: Mailbox, limit: int, offset: int) -> list[Message]:
        return (
            self.db.query(Message)
            .filter(Message.mailbox_id == mailbox.id, _not_expired())
            .order_by(Message.received_at.desc(), Message.id.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    def get_for_mailbox(self, mailbox: Mailbox, message_id: int) -> Optional[Message]:
        return (
            self.db.query(Message)
            .filter(Message.id == message_id, Message.mailbox_id == mailbox.id, _not_expired())
            .first()
        )

    def get_attachment_for_mailbox(self, mailbox: Mailbox, attachment_id: int) -> Optional[Attachment]:
        return (
            self.db.query(Attachment)
            .join(Message, Attachment.message_id == Message.id)
            .filter(
                Attachment.id == attachment_id,
                Message.mailbox_id == mailbox.id,
                _not_expired(),
            )
            .first()
        )

    def read_attachment(self, attachment: Attachment) -> bytes:
        if self.storage is None:
            raise StorageError("attachment storage is not available")
        return self.storage.get(attachment.storage_key)

    def set_read(self, message: Message, is_read: bool) -> Message:
        message.is_read = is_read
        self.db.commit()
        self.db.refresh(message)
        return message

    def delete(self, message: Message) -> None:
        keys = [attachment.storage_key for attachment in message.attachments]
        self.db.delete(message)
        self.db.commit()
        self._remove_objects(keys)
