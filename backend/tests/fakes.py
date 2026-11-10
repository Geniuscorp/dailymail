"""In-memory object storage used by route tests."""
from app.storage.base import StorageError


class InMemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.fail_puts_after: int | None = None
        self._puts = 0

    def put(self, key: str, data: bytes, content_type: str) -> None:
        if self.fail_puts_after is not None and self._puts >= self.fail_puts_after:
            raise StorageError("simulated outage")
        self._puts += 1
        self.objects[key] = (data, content_type)

    def get(self, key: str) -> bytes:
        if key not in self.objects:
            raise StorageError("missing object")
        return self.objects[key][0]

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)
