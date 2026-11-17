"""Admin request/response schemas."""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class AdminLogin(BaseModel):
    username: str = Field(..., min_length=1, max_length=150)
    password: str = Field(..., min_length=1)


class AdminDashboard(BaseModel):
    total_mailboxes: int
    active_mailboxes: int
    total_messages: int
    total_attachments: int
    storage_used_mb: float
    expiring_soon: int


class AdminMailbox(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email_address: str
    status: str
    batch_id: Optional[int] = None
    created_at: datetime
    message_count: int = 0


class AdminMailboxUpdate(BaseModel):
    status: Literal["active", "blocked", "deleted"]


class AdminMailboxPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[AdminMailbox]


class AdminBatch(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    quantity: int
    generation_type: str
    created_at: datetime
    mailbox_count: int = 0


class AdminBatchPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[AdminBatch]


class AdminPasswordReset(BaseModel):
    new_password: str = Field(..., min_length=8)


class AdminMessage(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    mailbox_id: int
    recipient: str
    sender: str
    subject: Optional[str] = None
    received_at: datetime
    expires_at: Optional[datetime] = None
    is_read: bool
    attachment_count: int


class AdminMessagePage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[AdminMessage]


class AdminAttachment(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    message_id: int
    original_filename: str
    mime_type: str
    file_size: int
    created_at: datetime


class AdminAttachmentPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[AdminAttachment]


# --- Overview ----------------------------------------------------------------


class MailboxCounts(BaseModel):
    total: int
    active: int
    blocked: int
    deleted: int


class MessageCounts(BaseModel):
    total: int
    unread: int
    last_24h: int
    last_7d: int
    expiring_soon: int
    expired_pending: int


class AttachmentCounts(BaseModel):
    total: int
    bytes: int
    largest_bytes: int
    average_bytes: int


class ActivityCounts(BaseModel):
    new_mailboxes_24h: int
    new_mailboxes_7d: int
    active_mailboxes_24h: int
    batches: int
    live_sessions: int
    admins: int


class DailyPoint(BaseModel):
    date: str
    messages: int
    mailboxes: int
    attachments: int
    attachment_bytes: int


class LabelCount(BaseModel):
    label: str
    count: int


class BusyMailbox(BaseModel):
    mailbox_id: int
    email_address: str
    count: int


class AttachmentTypeStat(BaseModel):
    mime_type: str
    count: int
    bytes: int


class AdminOverview(BaseModel):
    days: int
    mailboxes: MailboxCounts
    messages: MessageCounts
    attachments: AttachmentCounts
    activity: ActivityCounts
    series: list[DailyPoint]
    top_senders: list[LabelCount]
    top_sender_domains: list[LabelCount]
    busiest_mailboxes: list[BusyMailbox]
    attachment_types: list[AttachmentTypeStat]


# --- System ------------------------------------------------------------------


class BlockedClient(BaseModel):
    scope: str
    client: str
    count: int
    last_blocked_at: datetime


class LimiterStats(BaseModel):
    blocked_total: int
    recent_clients: int
    top_blocked: list[BlockedClient]


class ProtectionInfo(BaseModel):
    rate_limit_enabled: bool
    create_per_minute: int
    login_per_minute: int
    webhook_per_minute: int
    creation_secret_required: bool
    mailbox_session_days: int
    admin_token_minutes: int
    limiter: LimiterStats


class DatabaseInfo(BaseModel):
    dialect: str
    size_bytes: Optional[int] = None


class InboundInfo(BaseModel):
    provider: str
    webhook_secret_set: bool
    max_payload_mb: int


class StorageInfo(BaseModel):
    configured: bool
    bucket: Optional[str] = None
    max_attachment_mb: int
    max_attachments_per_message: int


class RetentionInfo(BaseModel):
    days: int
    sweep_enabled: bool
    sweep_interval_hours: int


class AdminSystem(BaseModel):
    app_name: str
    version: str
    environment: str
    debug: bool
    python: str
    uptime_seconds: int
    started_at: datetime
    domain: str
    database: DatabaseInfo
    inbound: InboundInfo
    storage: StorageInfo
    retention: RetentionInfo
    protection: ProtectionInfo


# --- Mailbox management ------------------------------------------------------


class AdminMailboxDetail(AdminMailbox):
    unread_count: int = 0
    attachment_count: int = 0
    storage_bytes: int = 0
    live_sessions: int = 0
    last_message_at: Optional[datetime] = None
    recent_messages: list[AdminMessage] = []


class AdminMailboxBulkStatus(BaseModel):
    ids: list[int] = Field(..., min_length=1, max_length=500)
    status: Literal["active", "blocked", "deleted"]


class AdminAffected(BaseModel):
    affected: int


# --- Message / attachment detail --------------------------------------------


class AdminMessageDetail(AdminMessage):
    text_body: Optional[str] = None
    attachments: list[AdminAttachment] = []


# --- Audit -------------------------------------------------------------------


class AdminAuditEntry(BaseModel):
    id: int
    admin_username: Optional[str] = None
    action: str
    target_type: str
    target_id: Optional[str] = None
    created_at: datetime


class AdminAuditPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[AdminAuditEntry]


# --- Administrators ----------------------------------------------------------


class AdminUserInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    status: str
    created_at: Optional[datetime] = None


class AdminUserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=150, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(..., min_length=10)


class AdminUserUpdate(BaseModel):
    status: Literal["active", "inactive"]


class AdminOwnPasswordChange(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=10)


class AdminMaintenanceResult(BaseModel):
    affected: int
