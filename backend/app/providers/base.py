"""Abstract inbound email provider interface."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


class InvalidWebhookError(Exception):
    """Raised when a webhook fails authentication or cannot be parsed."""


@dataclass(frozen=True)
class InboundAttachment:
    filename: Optional[str]
    declared_content_type: Optional[str]
    data: bytes


@dataclass(frozen=True)
class InboundMessage:
    provider_message_id: str
    sender: str
    recipient: str
    subject: Optional[str]
    text_body: Optional[str]
    html_body: Optional[str]
    received_at: Optional[datetime]
    attachments: tuple[InboundAttachment, ...] = field(default=())


class InboundEmailProvider(ABC):
    """Verifies and normalises webhook deliveries from an inbound email source."""

    @abstractmethod
    async def verify(self, headers: dict[str, str], raw_body: bytes, client_ip: Optional[str] = None) -> None:
        """Raise InvalidWebhookError if the delivery is not authentic.

        Async because not every provider can verify from the body alone: one
        that checks the caller's IP (e.g. via a reverse DNS lookup, which is
        a blocking call) needs this to not freeze the single event loop for
        the duration of that lookup.
        """

    @abstractmethod
    def parse(self, raw_body: bytes) -> InboundMessage:
        """Return a normalised message or raise InvalidWebhookError."""
