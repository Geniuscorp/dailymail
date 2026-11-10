"""Inbound message storage and mailbox message access."""
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

import nh3
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.mailbox import Mailbox, MailboxStatus
from app.models.message import Message
from app.providers.base import InboundMessage

HTML_ALLOWED_TAGS = {
    "a", "abbr", "b", "blockquote", "br", "code", "div", "em", "h1", "h2", "h3",
    "h4", "h5", "h6", "hr", "i", "li", "ol", "p", "pre", "small", "span",
    "strong", "table", "tbody", "td", "th", "thead", "tr", "u", "ul",
}


class IngestResult(str, Enum):
    STORED = "stored"
    DUPLICATE = "duplicate"
    IGNORED = "ignored"


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
    def __init__(self, db: Session):
        self.db = db
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
        self.db.add(message)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            return IngestResult.DUPLICATE
        return IngestResult.STORED

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
            .filter(Message.mailbox_id == mailbox.id)
            .order_by(Message.received_at.desc(), Message.id.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    def get_for_mailbox(self, mailbox: Mailbox, message_id: int) -> Optional[Message]:
        return (
            self.db.query(Message)
            .filter(Message.id == message_id, Message.mailbox_id == mailbox.id)
            .first()
        )

    def set_read(self, message: Message, is_read: bool) -> Message:
        message.is_read = is_read
        self.db.commit()
        self.db.refresh(message)
        return message

    def delete(self, message: Message) -> None:
        self.db.delete(message)
        self.db.commit()
