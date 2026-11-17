"""Read-only aggregates behind the admin overview and system pages."""
import os
import platform
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.rate_limit import limiter
from app.models.admin_user import AdminUser
from app.models.attachment import Attachment
from app.models.batch import Batch
from app.models.mailbox import Mailbox, MailboxStatus
from app.models.mailbox_session import MailboxSession
from app.models.message import Message

_STARTED_AT = time.time()
EXPIRING_SOON_DAYS = 7
TOP_N = 10
# Senders are grouped in SQL and folded into addresses/domains in Python, so cap
# how many distinct raw sender strings are pulled for the fold.
_SENDER_SCAN_LIMIT = 5000


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _count(db: Session, *criteria) -> int:
    return db.query(func.count()).select_from(Message).filter(*criteria).scalar() or 0


def _day_key(value: object) -> str:
    return str(value)[:10]


def _daily(db: Session, column, since: datetime, *extra) -> dict[str, tuple[int, int]]:
    """Per-day (row count, summed extra column) for rows created since ``since``."""
    day = func.date(column)
    selected = [day, func.count()]
    if extra:
        selected.append(func.coalesce(func.sum(extra[0]), 0))
    rows = db.query(*selected).filter(column >= since).group_by(day).all()
    return {_day_key(row[0]): (int(row[1]), int(row[2]) if extra else 0) for row in rows}


def _fold_senders(rows: list[tuple[str, int]]) -> tuple[list[dict], list[dict]]:
    by_address: Counter[str] = Counter()
    by_domain: Counter[str] = Counter()
    for raw, count in rows:
        address = parseaddr(raw or "")[1].lower() or (raw or "").strip().lower()
        if not address:
            continue
        by_address[address] += count
        by_domain[address.rpartition("@")[2] or address] += count
    return (
        [{"label": label, "count": count} for label, count in by_address.most_common(TOP_N)],
        [{"label": label, "count": count} for label, count in by_domain.most_common(TOP_N)],
    )


def build_overview(db: Session, days: int) -> dict:
    now = _now()
    window_start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    day_ago, week_ago = now - timedelta(days=1), now - timedelta(days=7)

    status_counts = dict(db.query(Mailbox.status, func.count()).group_by(Mailbox.status).all())
    by_status = {s.value: int(status_counts.get(s, 0)) for s in MailboxStatus}

    attachment_row = db.query(
        func.count(Attachment.id),
        func.coalesce(func.sum(Attachment.file_size), 0),
        func.coalesce(func.max(Attachment.file_size), 0),
    ).one()
    attachment_count, attachment_bytes, largest = (int(v) for v in attachment_row)

    mailbox_days = _daily(db, Mailbox.created_at, window_start)
    message_days = _daily(db, Message.received_at, window_start)
    attachment_days = _daily(db, Attachment.created_at, window_start, Attachment.file_size)

    series = []
    for offset in range(days):
        day = (window_start + timedelta(days=offset)).strftime("%Y-%m-%d")
        series.append(
            {
                "date": day,
                "messages": message_days.get(day, (0, 0))[0],
                "mailboxes": mailbox_days.get(day, (0, 0))[0],
                "attachments": attachment_days.get(day, (0, 0))[0],
                "attachment_bytes": attachment_days.get(day, (0, 0))[1],
            }
        )

    sender_rows = (
        db.query(func.lower(Message.sender), func.count())
        .filter(Message.received_at >= window_start)
        .group_by(func.lower(Message.sender))
        .order_by(func.count().desc())
        .limit(_SENDER_SCAN_LIMIT)
        .all()
    )
    top_senders, top_domains = _fold_senders([(r[0], int(r[1])) for r in sender_rows])

    busiest = (
        db.query(Mailbox.id, Mailbox.email_address, func.count(Message.id))
        .join(Message, Message.mailbox_id == Mailbox.id)
        .filter(Message.received_at >= window_start)
        .group_by(Mailbox.id, Mailbox.email_address)
        .order_by(func.count(Message.id).desc())
        .limit(TOP_N)
        .all()
    )

    types = (
        db.query(Attachment.mime_type, func.count(), func.coalesce(func.sum(Attachment.file_size), 0))
        .group_by(Attachment.mime_type)
        .order_by(func.count().desc())
        .limit(8)
        .all()
    )

    return {
        "days": days,
        "mailboxes": {"total": sum(by_status.values()), **by_status},
        "messages": {
            "total": _count(db),
            "unread": _count(db, Message.is_read.is_(False)),
            "last_24h": _count(db, Message.received_at >= day_ago),
            "last_7d": _count(db, Message.received_at >= week_ago),
            "expiring_soon": _count(
                db,
                Message.expires_at.isnot(None),
                Message.expires_at > now,
                Message.expires_at <= now + timedelta(days=EXPIRING_SOON_DAYS),
            ),
            "expired_pending": _count(db, Message.expires_at.isnot(None), Message.expires_at <= now),
        },
        "attachments": {
            "total": attachment_count,
            "bytes": attachment_bytes,
            "largest_bytes": largest,
            "average_bytes": attachment_bytes // attachment_count if attachment_count else 0,
        },
        "activity": {
            "new_mailboxes_24h": db.query(func.count(Mailbox.id)).filter(Mailbox.created_at >= day_ago).scalar() or 0,
            "new_mailboxes_7d": db.query(func.count(Mailbox.id)).filter(Mailbox.created_at >= week_ago).scalar() or 0,
            "active_mailboxes_24h": (
                db.query(func.count(func.distinct(Message.mailbox_id))).filter(Message.received_at >= day_ago).scalar()
                or 0
            ),
            "batches": db.query(func.count(Batch.id)).scalar() or 0,
            "live_sessions": db.query(func.count(MailboxSession.id)).filter(MailboxSession.expires_at > now).scalar() or 0,
            "admins": db.query(func.count(AdminUser.id)).scalar() or 0,
        },
        "series": series,
        "top_senders": top_senders,
        "top_sender_domains": top_domains,
        "busiest_mailboxes": [
            {"mailbox_id": row[0], "email_address": row[1], "count": int(row[2])} for row in busiest
        ],
        "attachment_types": [
            {"mime_type": row[0], "count": int(row[1]), "bytes": int(row[2])} for row in types
        ],
    }


def _sqlite_file_size(database_url: str) -> Optional[int]:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        return None
    path = database_url[len(prefix):]
    if not path or path.startswith(":memory:"):
        return None
    try:
        return os.path.getsize(path)
    except OSError:
        return None


def build_system_info(settings: Settings, *, version: str, storage_configured: bool) -> dict:
    return {
        "app_name": settings.app_name,
        "version": version,
        "environment": settings.environment,
        "debug": settings.debug,
        "python": platform.python_version(),
        "uptime_seconds": int(time.time() - _STARTED_AT),
        "started_at": datetime.fromtimestamp(_STARTED_AT, tz=timezone.utc),
        "domain": settings.domain,
        "database": {
            "dialect": settings.database_url.split(":", 1)[0].split("+", 1)[0],
            "size_bytes": _sqlite_file_size(settings.database_url),
        },
        "inbound": {
            "provider": settings.inbound_email_provider,
            "webhook_secret_set": bool(settings.inbound_webhook_secret),
            "max_payload_mb": settings.max_inbound_payload_mb,
        },
        "storage": {
            "configured": storage_configured,
            "bucket": settings.r2_bucket_name if storage_configured else None,
            "max_attachment_mb": settings.max_attachment_size_mb,
            "max_attachments_per_message": settings.max_attachments_per_message,
        },
        "retention": {
            "days": settings.email_retention_days,
            "sweep_enabled": settings.retention_sweep_enabled,
            "sweep_interval_hours": settings.retention_sweep_interval_hours,
        },
        "protection": {
            "rate_limit_enabled": settings.rate_limit_enabled,
            "create_per_minute": settings.rate_limit_create_per_minute,
            "login_per_minute": settings.rate_limit_login_per_minute,
            "webhook_per_minute": settings.rate_limit_webhook_per_minute,
            "creation_secret_required": bool(settings.mailbox_creation_secret),
            "mailbox_session_days": settings.mailbox_session_expire_days,
            "admin_token_minutes": settings.admin_token_expire_minutes,
            "limiter": limiter.stats(),
        },
    }
