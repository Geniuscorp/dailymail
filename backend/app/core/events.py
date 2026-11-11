"""In-process pub/sub so the inbox can be pushed new mail instead of polling.

The API runs a single uvicorn worker (see rate_limit.py and docs/DEPLOYMENT.md),
so an in-memory broker is enough and keeps the stack free of a message queue.
Move this to Redis pub/sub (or similar) if the API ever runs on more than one
process — a queue here would only reach whichever process holds it.
"""
import asyncio
from collections import defaultdict


class MailboxEventBroker:
    """Fan-out of one event per mailbox to every open SSE connection for it."""

    def __init__(self) -> None:
        self._subscribers: dict[int, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, mailbox_id: int) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=16)
        self._subscribers[mailbox_id].add(queue)
        return queue

    def unsubscribe(self, mailbox_id: int, queue: asyncio.Queue) -> None:
        subscribers = self._subscribers.get(mailbox_id)
        if subscribers is None:
            return
        subscribers.discard(queue)
        if not subscribers:
            self._subscribers.pop(mailbox_id, None)

    def publish(self, mailbox_id: int, event: str) -> None:
        for queue in list(self._subscribers.get(mailbox_id, ())):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # A stuck/slow client just misses this nudge; reconnecting
                # (or the fallback poll) still picks up the new message.
                pass


broker = MailboxEventBroker()
