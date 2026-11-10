"""Object storage interface for attachment bodies."""
from typing import Protocol


class StorageError(Exception):
    """Raised when an object cannot be stored, read or deleted."""


class ObjectStorage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...
