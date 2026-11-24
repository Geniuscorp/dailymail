"""Admin authentication, dashboard aggregates and management operations."""
import csv
import io
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password, verify_password
from app.models.admin_audit_log import AdminAuditLog
from app.models.admin_user import AdminUser, AdminUserStatus
from app.models.attachment import Attachment
from app.models.batch import Batch
from app.models.mailbox import Mailbox, MailboxStatus
from app.models.mailbox_session import MailboxSession
from app.models.message import Message
from app.schemas.admin import (
    AdminAttachment,
    AdminAuditEntry,
    AdminBatch,
    AdminMailbox,
    AdminMailboxDetail,
    AdminMessage,
    AdminMessageDetail,
)
from app.services.mailbox_service import MailboxService
from app.storage.base import ObjectStorage, StorageError

logger = logging.getLogger(__name__)

EXPIRING_SOON_DAYS = 7


class AdminRuleError(Exception):
    """An admin operation the service refuses on principle (not a bad request)."""


class AdminConflictError(Exception):
    """The requested admin account already exists."""


def _csv_safe(value: object) -> str:
    """Stop spreadsheet apps from running a cell that starts like a formula."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


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
        unread: Optional[bool] = None,
        has_attachments: Optional[bool] = None,
    ) -> tuple[int, list[AdminMessage]]:
        query = self.db.query(Message)
        if mailbox_id is not None:
            query = query.filter(Message.mailbox_id == mailbox_id)
        if unread is not None:
            query = query.filter(Message.is_read.is_(not unread))
        if has_attachments is not None:
            condition = Message.attachments.any()
            query = query.filter(condition if has_attachments else ~condition)
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
        self,
        limit: int,
        offset: int,
        message_id: Optional[int],
        search: Optional[str] = None,
    ) -> tuple[int, list[AdminAttachment]]:
        query = (
            self.db.query(Attachment, Message, Mailbox)
            .join(Message, Attachment.message_id == Message.id)
            .join(Mailbox, Message.mailbox_id == Mailbox.id)
        )
        if message_id is not None:
            query = query.filter(Attachment.message_id == message_id)
        if search:
            needle = f"%{search.strip().lower()}%"
            query = query.filter(
                or_(
                    func.lower(Attachment.original_filename).like(needle),
                    func.lower(Attachment.mime_type).like(needle),
                    func.lower(Mailbox.email_address).like(needle),
                    func.lower(Message.sender).like(needle),
                    func.lower(func.coalesce(Message.subject, "")).like(needle),
                )
            )

        total = query.count()
        rows = query.order_by(Attachment.id.desc()).limit(limit).offset(offset).all()
        items = [
            AdminAttachment(
                id=attachment.id,
                message_id=attachment.message_id,
                original_filename=attachment.original_filename,
                mime_type=attachment.mime_type,
                file_size=attachment.file_size,
                created_at=attachment.created_at,
                mailbox_id=mailbox.id,
                mailbox_email=mailbox.email_address,
                sender=message.sender,
                subject=message.subject,
                received_at=message.received_at,
            )
            for attachment, message, mailbox in rows
        ]
        return total, items

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

    def read_attachment(self, attachment: Attachment) -> bytes:
        if self.storage is None:
            raise StorageError("attachment storage is not configured")
        return self.storage.get(attachment.storage_key)

    # --- Login audit ----------------------------------------------------

    def record_login(self, admin: AdminUser) -> None:
        self._log(admin, "admin.login", "admin", admin.id)
        self.db.commit()

    # --- Audit log ------------------------------------------------------

    def list_audit(
        self, action_prefix: Optional[str], limit: int, offset: int
    ) -> tuple[int, list[AdminAuditEntry]]:
        query = self.db.query(AdminAuditLog, AdminUser.username).outerjoin(
            AdminUser, AdminUser.id == AdminAuditLog.admin_id
        )
        if action_prefix:
            query = query.filter(AdminAuditLog.action.like(f"{action_prefix}%"))

        total = query.count()
        rows = query.order_by(AdminAuditLog.id.desc()).limit(limit).offset(offset).all()
        return total, [
            AdminAuditEntry(
                id=log.id,
                admin_username=username,
                action=log.action,
                target_type=log.target_type,
                target_id=log.target_id,
                created_at=log.created_at,
            )
            for log, username in rows
        ]

    # --- Mailbox detail and bulk operations -----------------------------

    def mailbox_detail(self, mailbox: Mailbox) -> AdminMailboxDetail:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        messages = self.db.query(Message).filter(Message.mailbox_id == mailbox.id)
        unread = messages.filter(Message.is_read.is_(False)).count()
        last_at = (
            self.db.query(func.max(Message.received_at))
            .filter(Message.mailbox_id == mailbox.id)
            .scalar()
        )
        attachment_count, storage_bytes = (
            self.db.query(func.count(Attachment.id), func.coalesce(func.sum(Attachment.file_size), 0))
            .join(Message, Attachment.message_id == Message.id)
            .filter(Message.mailbox_id == mailbox.id)
            .one()
        )
        live_sessions = (
            self.db.query(func.count(MailboxSession.id))
            .filter(MailboxSession.mailbox_id == mailbox.id, MailboxSession.expires_at > now)
            .scalar()
            or 0
        )
        _, recent = self.list_messages(10, 0, mailbox.id, None)
        return AdminMailboxDetail.model_validate(mailbox).model_copy(
            update={
                "message_count": messages.count(),
                "unread_count": unread,
                "attachment_count": int(attachment_count),
                "storage_bytes": int(storage_bytes),
                "live_sessions": live_sessions,
                "last_message_at": last_at,
                "recent_messages": recent,
            }
        )

    def reset_mailbox_password(self, admin: AdminUser, mailbox: Mailbox, new_password: str) -> None:
        MailboxService(self.db).update_password(mailbox, new_password)
        self._log(admin, "mailbox.password", "mailbox", mailbox.id)
        self.db.commit()

    def revoke_mailbox_sessions(self, admin: AdminUser, mailbox: Mailbox) -> int:
        count = (
            self.db.query(func.count(MailboxSession.id))
            .filter(MailboxSession.mailbox_id == mailbox.id)
            .scalar()
            or 0
        )
        MailboxService(self.db).revoke_all_sessions(mailbox)
        self._log(admin, "mailbox.sessions_revoked", "mailbox", mailbox.id)
        self.db.commit()
        return count

    def bulk_set_mailbox_status(self, admin: AdminUser, ids: list[int], status: str) -> int:
        rows = self.db.query(Mailbox).filter(Mailbox.id.in_(set(ids))).all()
        for mailbox in rows:
            mailbox.status = MailboxStatus(status)
            self._log(admin, "mailbox.status", "mailbox", mailbox.id)
        self.db.commit()
        return len(rows)

    def clear_mailbox_messages(self, admin: AdminUser, mailbox: Mailbox) -> int:
        messages = self.db.query(Message).filter(Message.mailbox_id == mailbox.id).all()
        keys = [a.storage_key for message in messages for a in message.attachments]
        if keys and self.storage is None:
            raise StorageError("attachment storage is not configured")

        for message in messages:
            self.db.delete(message)
        self._log(admin, "mailbox.clear", "mailbox", mailbox.id)
        self.db.commit()

        for key in keys:
            try:
                self.storage.delete(key)
            except StorageError:
                logger.warning("orphaned attachment object %s could not be removed", key)
        return len(messages)

    def export_mailboxes_csv(self, search: Optional[str], status: Optional[str]) -> str:
        query = self.db.query(Mailbox)
        if search:
            query = query.filter(Mailbox.email_address.ilike(f"%{search.strip().lower()}%"))
        if status:
            query = query.filter(Mailbox.status == MailboxStatus(status))
        rows = query.order_by(Mailbox.id).all()
        counts = dict(
            self.db.query(Message.mailbox_id, func.count(Message.id)).group_by(Message.mailbox_id).all()
        )

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["id", "email_address", "status", "batch_id", "created_at", "message_count"])
        for row in rows:
            writer.writerow(
                [
                    row.id,
                    _csv_safe(row.email_address),
                    row.status.value if hasattr(row.status, "value") else row.status,
                    row.batch_id or "",
                    row.created_at.isoformat() if row.created_at else "",
                    counts.get(row.id, 0),
                ]
            )
        return buffer.getvalue()

    # --- Message detail -------------------------------------------------

    def message_detail(self, message: Message) -> AdminMessageDetail:
        # Validate against AdminMessage (no "attachments" field) first, not
        # AdminMessageDetail directly: from_attributes validation would
        # otherwise read message.attachments itself (the field name matches
        # the ORM relationship) and try to validate each raw Attachment row
        # against the richer AdminAttachment schema below, which needs
        # fields a bare row doesn't have.
        base = AdminMessage.model_validate(message)
        return AdminMessageDetail(
            **base.model_dump(),
            text_body=message.text_body,
            # AdminAttachment carries mailbox/sender context that isn't on
            # the Attachment row itself (see its definition) - here it's all
            # already on hand from the parent message, so no extra query is
            # needed, just a lazy load of message.mailbox.
            attachments=[
                AdminAttachment(
                    id=attachment.id,
                    message_id=attachment.message_id,
                    original_filename=attachment.original_filename,
                    mime_type=attachment.mime_type,
                    file_size=attachment.file_size,
                    created_at=attachment.created_at,
                    mailbox_id=message.mailbox_id,
                    mailbox_email=message.mailbox.email_address,
                    sender=message.sender,
                    subject=message.subject,
                    received_at=message.received_at,
                )
                for attachment in message.attachments
            ],
        )

    # --- Administrators -------------------------------------------------

    def list_admins(self) -> list[AdminUser]:
        return self.db.query(AdminUser).order_by(AdminUser.id).all()

    def get_admin(self, admin_id: int) -> Optional[AdminUser]:
        return self.db.query(AdminUser).filter(AdminUser.id == admin_id).first()

    def create_admin(self, actor: AdminUser, username: str, password: str) -> AdminUser:
        if self.db.query(AdminUser.id).filter(AdminUser.username == username).first() is not None:
            raise AdminConflictError("Admin username already exists")
        admin = AdminUser(
            username=username,
            password_hash=hash_password(password),
            status=AdminUserStatus.ACTIVE,
        )
        self.db.add(admin)
        self.db.flush()
        self._log(actor, "admin.create", "admin", admin.id)
        self.db.commit()
        self.db.refresh(admin)
        return admin

    def set_admin_status(self, actor: AdminUser, target: AdminUser, status: str) -> AdminUser:
        new_status = AdminUserStatus(status)
        if new_status == AdminUserStatus.INACTIVE:
            if target.id == actor.id:
                raise AdminRuleError("You cannot deactivate your own account")
            active = self.db.query(func.count(AdminUser.id)).filter(
                AdminUser.status == AdminUserStatus.ACTIVE
            ).scalar() or 0
            if target.status == AdminUserStatus.ACTIVE and active <= 1:
                raise AdminRuleError("At least one active admin is required")
        target.status = new_status
        self._log(actor, "admin.status", "admin", target.id)
        self.db.commit()
        self.db.refresh(target)
        return target

    def change_own_password(self, admin: AdminUser, current: str, new: str) -> bool:
        if not verify_password(current, admin.password_hash):
            return False
        admin.password_hash = hash_password(new)
        self._log(admin, "admin.password", "admin", admin.id)
        self.db.commit()
        return True

    # --- Maintenance ----------------------------------------------------

    def purge_expired_messages(self, admin: AdminUser) -> int:
        from app.tasks.retention import purge_expired_messages

        purged = purge_expired_messages(self.db, self.storage)
        self._log(admin, "maintenance.purge_messages", "system", purged)
        self.db.commit()
        return purged

    def purge_expired_sessions(self, admin: AdminUser) -> int:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        removed = (
            self.db.query(MailboxSession)
            .filter(MailboxSession.expires_at <= now)
            .delete(synchronize_session=False)
        )
        self._log(admin, "maintenance.purge_sessions", "system", removed)
        self.db.commit()
        return removed
