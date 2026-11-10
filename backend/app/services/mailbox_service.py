"""Mailbox business logic."""
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional

from app.models.mailbox import Mailbox, MailboxStatus
from app.models.batch import Batch, BatchGenerationType
from app.core.security import (
    hash_password,
    verify_password,
    generate_batch_addresses,
    is_reserved_address,
    normalize_address,
)
from app.core.config import get_settings

settings = get_settings()


class MailboxValidationError(ValueError):
    """The request is invalid (bad domain, bad address, inconsistent payload)."""


class MailboxConflictError(ValueError):
    """The address is reserved or already taken."""


class MailboxService:
    """Service for mailbox operations."""

    def __init__(self, db: Session):
        self.db = db

    def email_exists(self, email_address: str) -> bool:
        """Check if the address is already registered.

        Deleted mailboxes keep their row (and the unique index on the address), so
        they count as taken: the address cannot be recycled, and the check stays
        consistent with the constraint instead of surfacing a 500 on insert.
        """
        return (
            self.db.query(Mailbox.id)
            .filter(Mailbox.email_address == email_address.lower())
            .first()
            is not None
        )

    def is_address_valid(self, email_address: str) -> bool:
        """Check if address is valid and not reserved."""
        local_part = email_address.split("@")[0]
        return not is_reserved_address(local_part)

    def _validate_address(self, email_address: str) -> str:
        """Normalize an address and require it to belong to the service domain."""
        try:
            address = normalize_address(email_address, settings.domain)
        except ValueError as exc:
            raise MailboxValidationError(str(exc)) from exc

        if not self.is_address_valid(address):
            raise MailboxConflictError(f"Address '{address}' is reserved")
        return address

    def create_mailbox(
        self,
        email_address: str,
        password: str,
        batch_id: Optional[int] = None,
    ) -> Mailbox:
        """Create a new mailbox.

        Raises:
            MailboxValidationError: If the address is malformed or on another domain
            MailboxConflictError: If the address is reserved or already exists
        """
        email_lower = self._validate_address(email_address)

        if self.email_exists(email_lower):
            raise MailboxConflictError(f"Email '{email_lower}' already exists")

        # Mailboxes do not expire: only their content does. The account and its
        # credentials stay valid until the owner deletes it.
        mailbox = Mailbox(
            email_address=email_lower,
            password_hash=hash_password(password),
            batch_id=batch_id,
            status=MailboxStatus.ACTIVE,
        )

        self.db.add(mailbox)
        try:
            self.db.commit()
        except IntegrityError:
            # Lost a race against a concurrent creation of the same address.
            self.db.rollback()
            raise MailboxConflictError(f"Email '{email_lower}' already exists") from None
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

        Raises:
            MailboxValidationError: If an address is malformed or on another domain
            MailboxConflictError: If an address is reserved or already exists
        """
        if generation_type == "custom":
            if not custom_addresses:
                raise MailboxValidationError("custom_addresses is required for custom generation")
            addresses = [self._validate_address(addr) for addr in custom_addresses]
        else:
            addresses = [
                self._validate_address(f"{local_part}@{settings.domain}")
                for local_part in generate_batch_addresses(quantity, prefix)
            ]

        # Check all addresses are available
        if len(set(addresses)) != len(addresses):
            raise MailboxValidationError("The request contains duplicate addresses")

        for addr in addresses:
            if self.email_exists(addr):
                raise MailboxConflictError(f"Email '{addr}' already exists")

        # Every mailbox in a batch shares one password, so hash it once: Argon2 is
        # deliberately slow and hashing per mailbox made a 100-address batch take
        # about ten seconds inside a synchronous request.
        shared_hash = hash_password(password)

        # Create batch
        batch = Batch(
            quantity=len(addresses),
            generation_type=BatchGenerationType(generation_type),
            password_hash=shared_hash,
        )

        self.db.add(batch)
        self.db.flush()  # Get batch ID

        # Create mailboxes (accounts persist; only messages expire)
        mailboxes = []

        for addr in addresses:
            mailbox = Mailbox(
                email_address=addr,
                password_hash=shared_hash,
                batch_id=batch.id,
                status=MailboxStatus.ACTIVE,
            )
            mailboxes.append(mailbox)
            self.db.add(mailbox)

        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise MailboxConflictError("One of the requested addresses already exists") from None
        self.db.refresh(batch)

        return batch, mailboxes

    def get_mailbox(self, email_address: str) -> Optional[Mailbox]:
        """Get an usable mailbox by email (blocked and deleted accounts do not log in)."""
        return (
            self.db.query(Mailbox)
            .filter(
                Mailbox.email_address == email_address.lower(),
                Mailbox.status == MailboxStatus.ACTIVE,
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
        # One hash for the whole batch: they all share the same password anyway.
        shared_hash = hash_password(new_password)
        batch.password_hash = shared_hash

        # Update all mailboxes in batch
        mailboxes = (
            self.db.query(Mailbox)
            .filter(Mailbox.batch_id == batch.id)
            .all()
        )

        for mailbox in mailboxes:
            mailbox.password_hash = shared_hash

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
