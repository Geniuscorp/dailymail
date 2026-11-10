"""Mailbox business logic."""
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.models.mailbox import Mailbox, MailboxStatus
from app.models.batch import Batch, BatchGenerationType
from app.core.security import (
    hash_password,
    verify_password,
    generate_batch_addresses,
    is_reserved_address,
)
from app.core.config import get_settings

settings = get_settings()


class MailboxService:
    """Service for mailbox operations."""

    def __init__(self, db: Session):
        self.db = db

    def email_exists(self, email_address: str) -> bool:
        """Check if email address already exists."""
        return (
            self.db.query(Mailbox)
            .filter(
                Mailbox.email_address == email_address.lower(),
                Mailbox.status != MailboxStatus.DELETED,
            )
            .first()
            is not None
        )

    def is_address_valid(self, email_address: str) -> bool:
        """Check if address is valid and not reserved."""
        local_part = email_address.split("@")[0]
        return not is_reserved_address(local_part)

    def create_mailbox(
        self,
        email_address: str,
        password: str,
        batch_id: Optional[int] = None,
    ) -> Mailbox:
        """Create a new mailbox.

        Raises:
            ValueError: If email already exists or is invalid
        """
        email_lower = email_address.lower()

        # Validate
        if not self.is_address_valid(email_lower):
            raise ValueError(f"Address '{email_lower}' is reserved")

        if self.email_exists(email_lower):
            raise ValueError(f"Email '{email_lower}' already exists")

        # Calculate expiration (30 days from now)
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.email_retention_days)

        # Create mailbox
        mailbox = Mailbox(
            email_address=email_lower,
            password_hash=hash_password(password),
            batch_id=batch_id,
            status=MailboxStatus.ACTIVE,
            expires_at=expires_at,
        )

        self.db.add(mailbox)
        self.db.commit()
        self.db.refresh(mailbox)

        return mailbox

    def create_batch(
        self,
        quantity: int,
        password: str,
        generation_type: str = "random",
        prefix: Optional[str] = None,
        custom_addresses: Optional[list[str]] = None,
    ) -> tuple[Batch, list[Mailbox]]:
        """Create a batch of mailboxes.

        Returns:
            (batch, mailboxes)
        """
        # Generate addresses
        if generation_type == "custom" and custom_addresses:
            addresses = custom_addresses
        else:
            addresses = generate_batch_addresses(quantity, prefix)

        # Check all addresses are available
        for addr in addresses:
            if self.email_exists(addr):
                raise ValueError(f"Email '{addr}' already exists")
            if not self.is_address_valid(addr):
                raise ValueError(f"Address '{addr}' is reserved")

        # Create batch
        batch = Batch(
            quantity=len(addresses),
            generation_type=BatchGenerationType(generation_type),
            password_hash=hash_password(password),
        )

        self.db.add(batch)
        self.db.flush()  # Get batch ID

        # Create mailboxes
        mailboxes = []
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.email_retention_days)

        for addr in addresses:
            mailbox = Mailbox(
                email_address=addr.lower(),
                password_hash=hash_password(password),
                batch_id=batch.id,
                status=MailboxStatus.ACTIVE,
                expires_at=expires_at,
            )
            mailboxes.append(mailbox)
            self.db.add(mailbox)

        self.db.commit()
        self.db.refresh(batch)

        return batch, mailboxes

    def get_mailbox(self, email_address: str) -> Optional[Mailbox]:
        """Get mailbox by email."""
        return (
            self.db.query(Mailbox)
            .filter(
                Mailbox.email_address == email_address.lower(),
                Mailbox.status != MailboxStatus.DELETED,
            )
            .first()
        )

    def authenticate_mailbox(self, email_address: str, password: str) -> Optional[Mailbox]:
        """Authenticate mailbox with email and password."""
        mailbox = self.get_mailbox(email_address)

        if not mailbox:
            return None

        if not verify_password(password, mailbox.password_hash):
            return None

        return mailbox

    def update_password(self, mailbox: Mailbox, new_password: str) -> Mailbox:
        """Update mailbox password."""
        mailbox.password_hash = hash_password(new_password)
        self.db.commit()
        self.db.refresh(mailbox)
        return mailbox

    def delete_mailbox(self, mailbox: Mailbox) -> None:
        """Soft delete mailbox."""
        mailbox.status = MailboxStatus.DELETED
        self.db.commit()

    def get_batch(self, batch_id: int) -> Optional[Batch]:
        """Get batch by ID."""
        return self.db.query(Batch).filter(Batch.id == batch_id).first()

    def update_batch_password(self, batch: Batch, new_password: str) -> Batch:
        """Update password for all mailboxes in batch."""
        # Update batch password hash
        batch.password_hash = hash_password(new_password)

        # Update all mailboxes in batch
        mailboxes = (
            self.db.query(Mailbox)
            .filter(Mailbox.batch_id == batch.id)
            .all()
        )

        for mailbox in mailboxes:
            mailbox.password_hash = hash_password(new_password)

        self.db.commit()
        self.db.refresh(batch)

        return batch

    def get_batch_mailboxes(self, batch_id: int, limit: int = 100, offset: int = 0) -> list[Mailbox]:
        """Get mailboxes in a batch."""
        return (
            self.db.query(Mailbox)
            .filter(Mailbox.batch_id == batch_id)
            .limit(limit)
            .offset(offset)
            .all()
        )

    def get_mailbox_count(self) -> int:
        """Get total active mailbox count."""
        return (
            self.db.query(func.count(Mailbox.id))
            .filter(Mailbox.status == MailboxStatus.ACTIVE)
            .scalar()
        )

    def get_batch_count(self) -> int:
        """Get total batch count."""
        return self.db.query(func.count(Batch.id)).scalar()
