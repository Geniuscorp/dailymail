"""In-process rate limiting for the endpoints that are open to the internet.

Counters live in this process, so each uvicorn worker has its own budget. That
keeps a single-host deployment free of an external store (Redis); it is still
enough to stop password guessing and bulk mailbox creation from one client. Move
the counters to a shared store if the API ever runs on several hosts.

Client identification uses ``request.client``, which uvicorn rewrites from
``X-Forwarded-For`` only when told to trust the proxy in front of it
(``--proxy-headers --forwarded-allow-ips``, set in ``backend/Dockerfile`` for
the Compose deployment and already the default for the systemd + local-nginx
option in the deployment guide, since there the proxy is 127.0.0.1). Without
that trust every request looks like it comes from the proxy's own address and
this becomes one shared budget for every real visitor.
"""
import logging
import math
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Deque, Optional

from fastapi import HTTPException, Request, status

from app.core.config import get_settings

logger = logging.getLogger(__name__)


# Bounds the memory the "who got blocked" report can hold.
_MAX_TRACKED_BLOCKED = 500


class SlidingWindowLimiter:
    """Counts events per key inside a sliding window."""

    def __init__(self) -> None:
        self._hits: dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._blocked_total = 0
        # key -> [times blocked, wall-clock time of the last block]
        self._blocked: dict[str, list[float]] = {}

    def hit(
        self,
        key: str,
        limit: int,
        window_seconds: int,
        now: Optional[float] = None,
    ) -> Optional[float]:
        """Record one event.

        Returns:
            ``None`` when the event is allowed, otherwise the seconds to wait
            before the window frees a slot.
        """
        if limit <= 0:
            return None

        moment = time.monotonic() if now is None else now
        with self._lock:
            timestamps = self._hits[key]
            cutoff = moment - window_seconds
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()

            if len(timestamps) >= limit:
                self._record_block(key)
                return timestamps[0] + window_seconds - moment

            timestamps.append(moment)
            return None

    def _record_block(self, key: str) -> None:
        self._blocked_total += 1
        entry = self._blocked.get(key)
        if entry is None:
            if len(self._blocked) >= _MAX_TRACKED_BLOCKED:
                oldest = min(self._blocked, key=lambda k: self._blocked[k][1])
                del self._blocked[oldest]
            entry = self._blocked[key] = [0, 0.0]
        entry[0] += 1
        entry[1] = time.time()

    def stats(self, window_seconds: int = 60, top: int = 10) -> dict:
        """Snapshot for the admin panel: who is being limited, since this process started."""
        moment = time.monotonic()
        with self._lock:
            recent = sum(
                1 for stamps in self._hits.values() if stamps and stamps[-1] > moment - window_seconds
            )
            ranked = sorted(self._blocked.items(), key=lambda item: item[1][0], reverse=True)[:top]
            blocked = []
            for key, (count, last) in ranked:
                scope, _, client = key.partition(":")
                blocked.append(
                    {
                        "scope": scope,
                        "client": client,
                        "count": int(count),
                        "last_blocked_at": datetime.fromtimestamp(last, tz=timezone.utc),
                    }
                )
            return {
                "blocked_total": self._blocked_total,
                "recent_clients": recent,
                "top_blocked": blocked,
            }

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
            self._blocked.clear()
            self._blocked_total = 0


limiter = SlidingWindowLimiter()


def rate_limited(scope: str, limit_setting: str, window_seconds: int = 60):
    """Build a FastAPI dependency enforcing the limit named by ``limit_setting``."""

    async def dependency(request: Request) -> None:
        settings = get_settings()
        if not settings.rate_limit_enabled:
            return

        client = request.client.host if request.client else "unknown"
        limit = getattr(settings, limit_setting)
        retry_after = limiter.hit(f"{scope}:{client}", limit, window_seconds)
        if retry_after is not None:
            logger.warning(
                "rate limited scope=%s client=%s xff=%r retry_after=%.0fs",
                scope,
                client,
                request.headers.get("x-forwarded-for"),
                retry_after,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests, try again later",
                headers={"Retry-After": str(max(1, math.ceil(retry_after)))},
            )

    return dependency
