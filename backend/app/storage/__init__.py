"""Storage providers for attachments."""
from functools import lru_cache

from app.core.config import get_settings
from app.storage.base import ObjectStorage, StorageError
from app.storage.r2 import R2Storage

__all__ = ["ObjectStorage", "StorageError", "StorageNotConfiguredError", "get_object_storage"]


class StorageNotConfiguredError(RuntimeError):
    pass


@lru_cache()
def get_object_storage() -> ObjectStorage:
    settings = get_settings()
    endpoint = settings.r2_endpoint_url or (
        f"https://{settings.r2_account_id}.r2.cloudflarestorage.com" if settings.r2_account_id else ""
    )
    if not (endpoint and settings.r2_access_key_id and settings.r2_secret_access_key and settings.r2_bucket_name):
        raise StorageNotConfiguredError("R2 credentials are not configured")
    return R2Storage(
        endpoint_url=endpoint,
        bucket=settings.r2_bucket_name,
        access_key_id=settings.r2_access_key_id,
        secret_access_key=settings.r2_secret_access_key,
    )
