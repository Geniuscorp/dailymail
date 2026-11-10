"""Retention sweep: delete messages past their expiry and their stored attachments.

Expired messages are already invisible through the API (see MessageService); this
job is what actually reclaims database rows and R2 objects. Run it from cron or a
systemd timer:

    cd backend && .venv/bin/python -m app.tasks.retention

Exit code 0 means the sweep ran; 1 means attachments were due but object storage
is not configured, so nothing was deleted and the next run will retry.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.message import Message
from app.storage import StorageNotConfiguredError, get_object_storage
from app.storage.base import ObjectStorage, StorageError

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 200


def _cutoff(now: Optional[datetime]) -> datetime:
    reference = now or datetime.now(timezone.utc)
    return reference.astimezone(timezone.utc).replace(tzinfo=None)


def _delete_objects(storage: Optional[ObjectStorage], keys: list[str]) -> None:
    if not keys:
        return
    if storage is None:
        raise StorageError("attachment storage is not available")
    for key in keys:
        try:
            storage.delete(key)
        except StorageError:
            # The message row still goes away (its content is no longer readable),
            # but the orphaned object needs a manual purge; keep the key in the log.
            logger.warning("orphaned attachment object %s could not be removed", key)


def purge_expired_messages(
    db: Session,
    storage: Optional[ObjectStorage] = None,
    now: Optional[datetime] = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    """Delete expired messages in batches, removing their attachments first.

    Returns the number of messages removed.
    """
    cutoff = _cutoff(now)
    purged = 0

    while True:
        expired = (
            db.query(Message)
            .filter(Message.expires_at.isnot(None), Message.expires_at <= cutoff)
            .order_by(Message.id)
            .limit(batch_size)
            .all()
        )
        if not expired:
            return purged

        keys = [attachment.storage_key for message in expired for attachment in message.attachments]
        if keys and storage is None:
            raise StorageError("attachment storage is not configured; refusing to drop attachment metadata")

        _delete_objects(storage, keys)

        for message in expired:
            db.delete(message)
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

        purged += len(expired)
        logger.info("retention sweep removed %s expired message(s)", len(expired))


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    storage: Optional[ObjectStorage] = None
    try:
        storage = get_object_storage()
    except StorageNotConfiguredError:
        logger.warning("object storage is not configured; messages with attachments will not be purged")

    db = SessionLocal()
    try:
        purged = purge_expired_messages(db, storage)
    except StorageError as exc:
        logger.error("retention sweep aborted: %s", exc)
        return 1
    finally:
        db.close()

    logger.info("retention sweep finished: %s message(s) purged", purged)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
