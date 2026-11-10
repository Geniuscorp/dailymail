"""Admin authentication, dashboard aggregates and management operations."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import verify_password
from app.models.admin_audit_log import AdminAuditLog
from app.models.admin_user import AdminUser, AdminUserStatus
from app.models.attachment import Attachment
from app.models.batch import Batch
from app.models.mailbox import Mailbox, MailboxStatus
from app.models.message import Message
from app.schemas.admin import (
    AdminAttachment,
    AdminBatch,
    AdminMailbox,
    AdminMessage,
)
from app.services.mailbox_service import MailboxService
from app.storage.base import ObjectStorage, StorageError

logger = logging.getLogger(__name__)

EXPIRING_SOON_DAYS = 7


def _naive_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None)


class AdminService:
    def __init__(self, db: Session, storage: Optional[ObjectStorage] = None):
        self.db = db
        self.storage = storage
        self.settings = get_settings()

    # --- Authentication -------------------------------------------------

    def _ensure_bootstrap_admin(self) -> None:
        """Create the env-configured admin the first time nobody exists yet."""
        if not self.settings.admin_password_hash:
            return
        if self.db.query(AdminUser.id).first() is not None:
            return
        self.db.add(
            AdminUser(
                username=self.settings.admin_username,
                password_hash=self.settings.admin_password_hash,
                status=AdminUserStatus.ACTIVE,
            )
        )
        self.db.commit()

    def authenticate(self, username: str, password: str) -> Optional[AdminUser]:
        self._ensure_bootstrap_admin()
        admin = (
            self.db.query(AdminUser)
            .filter(
                AdminUser.username == username,
                AdminUser.status == AdminUserStatus.ACTIVE,
            )
            .first()
        )
        if admin is None or not verify_password(password, admin.password_hash):
            return None
        return admin

    def is_configured(self) -> bool:
        return bool(self.settings.admin_password_hash) or (
            self.db.query(AdminUser.id).first() is not None
        )

    # --- Audit ----------------------------------------------------------

    def _log(self, admin: AdminUser, action: str, target_type: str, target_id: object | None) -> None:
        self.db.add(
            AdminAuditLog(
                admin_id=admin.id,
                action=action,
                target_type=target_type,
                target_id=None if target_id is None else str(target_id),
            )
        )

    # --- Dashboard ------------------------------------------------------

    def dashboard(self) -> dict:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        storage_bytes = self.db.query(func.coalesce(func.sum(Attachment.file_size), 0)).scalar() or 0
        return {
            "total_mailboxes": self.db.query(func.count(Mailbox.id)).scalar() or 0,
            "active_mailboxes": (
                self.db.query(func.count(Mailbox.id))
                .filter(Mailbox.status == MailboxStatus.ACTIVE)
                .scalar()
                or 0
            ),
            "total_messages": self.db.query(func.count(Message.id)).scalar() or 0,
            "total_attachments": self.db.query(func.count(Attachment.id)).scalar() or 0,
            "storage_used_mb": round(storage_bytes / (1024 * 1024), 2),
            "expiring_soon": (
                self.db.query(func.count(Message.id))
                .filter(
                    Message.expires_at.isnot(None),
                    Message.expires_at > now,
                    Message.expires_at <= now + timedelta(days=EXPIRING_SOON_DAYS),
                )
                .scalar()
                or 0
            ),
        }

    # --- Mailboxes ------------------------------------------------------

    def list_mailboxes(
        self,
        search: Optional[str],
        status: Optional[str],
        limit: int,
        offset: int,
    ) -> tuple[int, list[AdminMailbox]]:
        query = self.db.query(Mailbox)
        if search:
            query = query.filter(Mailbox.email_address.ilike(f"%{search.strip().lower()}%"))
        if status:
            query = query.filter(Mailbox.status == MailboxStatus(status))

        total = query.count()
        rows = query.order_by(Mailbox.id.desc()).limit(limit).offset(offset).all()

        ids = [row.id for row in rows]
        counts: dict[int, int] = {}
        if ids:
            counts = dict(
                self.db.query(Message.mailbox_id, func.count(Message.id))
                .filter(Message.mailbox_id.in_(ids))
                .group_by(Message.mailbox_id)
                .all()
            )

        items = [
            AdminMailbox.model_validate(row).model_copy(
                update={"message_count": counts.get(row.id, 0)}
            )
            for row in rows
        ]
        return total, items

    def get_mailbox(self, mailbox_id: int) -> Optional[Mailbox]:
        return self.db.query(Mailbox).filter(Mailbox.id == mailbox_id).first()

    def count_messages(self, mailbox_id: int) -> int:
        return (
            self.db.query(func.count(Message.id))
            .filter(Message.mailbox_id == mailbox_id)
            .scalar()
            or 0
        )

    def set_mailbox_status(self, admin: AdminUser, mailbox: Mailbox, status: str) -> Mailbox:
        mailbox.status = MailboxStatus(status)
        self._log(admin, "mailbox.status", "mailbox", mailbox.id)
        self.db.commit()
        self.db.refresh(mailbox)
        return mailbox

    def delete_mailbox(self, admin: AdminUser, mailbox: Mailbox) -> None:
        """Soft delete: the account stops working, its messages age out normally."""
        mailbox.status = MailboxStatus.DELETED
        self._log(admin, "mailbox.delete", "mailbox", mailbox.id)
        self.db.commit()

    # --- Batches --------------------------------------------------------

    def list_batches(self, limit: int, offset: int) -> tuple[int, list[AdminBatch]]:
        total = self.db.query(func.count(Batch.id)).scalar() or 0
        rows = self.db.query(Batch).order_by(Batch.id.desc()).limit(limit).offset(offset).all()

        ids = [row.id for row in rows]
        counts: dict[int, int] = {}
        if ids:
            counts = dict(
                self.db.query(Mailbox.batch_id, func.count(Mailbox.id))
                .filter(Mailbox.batch_id.in_(ids))
                .group_by(Mailbox.batch_id)
                .all()
            )

        items = [
            AdminBatch.model_validate(row).model_copy(
                update={"mailbox_count": counts.get(row.id, 0)}
            )
            for row in rows
        ]
        return total, items

    def get_batch(self, batch_id: int) -> Optional[Batch]:
        return self.db.query(Batch).filter(Batch.id == batch_id).first()

    def reset_batch_password(self, admin: AdminUser, batch: Batch, new_password: str) -> Batch:
        updated = MailboxService(self.db).update_batch_password(batch, new_password)
        self._log(admin, "batch.password", "batch", batch.id)
        self.db.commit()
        return updated

    # --- Messages -------------------------------------------------------

    def list_messages(
        self,
        limit: int,
        offset: int,
        mailbox_id: Optional[int],
        search: Optional[str],
    ) -> tuple[int, list[AdminMessage]]:
        query = self.db.query(Message)
        if mailbox_id is not None:
            query = query.filter(Message.mailbox_id == mailbox_id)
        if search:
            needle = f"%{search.strip().lower()}%"
            query = query.filter(
                or_(
                    func.lower(Message.sender).like(needle),
                    func.lower(Message.recipient).like(needle),
                    func.lower(func.coalesce(Message.subject, "")).like(needle),
                )
            )

        total = query.count()
        rows = (
            query.order_by(Message.received_at.desc(), Message.id.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )
        return total, [AdminMessage.model_validate(row) for row in rows]

    def get_message(self, message_id: int) -> Optional[Message]:
        return self.db.query(Message).filter(Message.id == message_id).first()

    def delete_message(self, admin: AdminUser, message: Message) -> None:
        keys = [attachment.storage_key for attachment in message.attachments]
        if keys and self.storage is None:
            raise StorageError("attachment storage is not configured")

        message_id = message.id
        self.db.delete(message)
        self._log(admin, "message.delete", "message", message_id)
        self.db.commit()

        for key in keys:
            try:
                self.storage.delete(key)
            except StorageError:
                logger.warning("orphaned attachment object %s could not be removed", key)

    # --- Attachments ----------------------------------------------------

    def list_attachments(
        self, limit: int, offset: int, message_id: Optional[int]
    ) -> tuple[int, list[AdminAttachment]]:
        query = self.db.query(Attachment)
        if message_id is not None:
            query = query.filter(Attachment.message_id == message_id)

        total = query.count()
        rows = query.order_by(Attachment.id.desc()).limit(limit).offset(offset).all()
        return total, [AdminAttachment.model_validate(row) for row in rows]

    def get_attachment(self, attachment_id: int) -> Optional[Attachment]:
        return self.db.query(Attachment).filter(Attachment.id == attachment_id).first()

    def delete_attachment(self, admin: AdminUser, attachment: Attachment) -> None:
        if self.storage is None:
            raise StorageError("attachment storage is not configured")

        key = attachment.storage_key
        attachment_id = attachment.id
        self.db.delete(attachment)
        self._log(admin, "attachment.delete", "attachment", attachment_id)
        self.db.commit()

        try:
            self.storage.delete(key)
        except StorageError:
            logger.warning("orphaned attachment object %s could not be removed", key)
