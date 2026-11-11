"""Tests for the mailbox event broker and the SSE push endpoint."""
import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient

import app.api.messages as messages_module
from app.api.messages import _mailbox_event_source
from app.core.config import get_settings
from app.core.events import MailboxEventBroker, broker
from app.main import app
from tests.conftest import TestingSessionLocal

client = TestClient(app)
DOMAIN = get_settings().domain


class TestMailboxEventBroker:
    """The broker itself: plain pub/sub, no FastAPI involved."""

    def test_publish_reaches_only_subscribers_of_that_mailbox(self):
        test_broker = MailboxEventBroker()
        mine = test_broker.subscribe(1)
        other = test_broker.subscribe(2)

        test_broker.publish(1, "new_message")

        assert mine.get_nowait() == "new_message"
        with pytest.raises(asyncio.QueueEmpty):
            other.get_nowait()

    def test_unsubscribe_stops_delivery(self):
        test_broker = MailboxEventBroker()
        queue = test_broker.subscribe(1)
        test_broker.unsubscribe(1, queue)

        test_broker.publish(1, "new_message")  # no subscribers left; must not raise

        with pytest.raises(asyncio.QueueEmpty):
            queue.get_nowait()

    def test_publish_with_no_subscribers_is_a_noop(self):
        test_broker = MailboxEventBroker()
        test_broker.publish(999, "new_message")  # must not raise


class TestStreamEndpointAuth:
    """Only the rejection paths: these return before the body ever streams,
    so the sync TestClient handles them fine (see TestMailboxEventSource for
    why the generator itself is tested differently).
    """

    @pytest.fixture(autouse=True)
    def _use_test_database_for_stream_auth(self, monkeypatch):
        # The route resolves the token with its own short-lived session
        # (see its docstring) instead of the request-scoped `get_db`
        # dependency the rest of the suite overrides, so it needs its own
        # patch to land on the same in-memory test database.
        monkeypatch.setattr(messages_module, "SessionLocal", TestingSessionLocal)

    def test_stream_requires_authentication(self):
        assert client.get("/api/messages/stream").status_code == 403

    def test_stream_rejects_garbage_token(self):
        response = client.get(
            "/api/messages/stream", headers={"Authorization": "Bearer not-a-real-token"}
        )
        assert response.status_code == 401


class TestMailboxEventSource:
    """Drives the SSE generator directly, bypassing HTTP entirely.

    Every in-process ASGI transport available here (Starlette's TestClient,
    httpx.ASGITransport) only returns a response after the app's generator
    finishes — which this one, by design, never does on its own. Calling
    `_mailbox_event_source` as a plain async generator is what actually lets
    a test observe "ready" first and a real push second, the same body the
    HTTP route streams out, without the transport's full-buffering getting
    in the way.
    """

    @pytest.mark.asyncio
    async def test_yields_ready_first(self):
        mailbox_id = 1001
        gen = _mailbox_event_source(mailbox_id)
        try:
            first = await asyncio.wait_for(gen.__anext__(), timeout=1)
            assert first == "event: ready\ndata: {}\n\n"
        finally:
            await gen.aclose()

    @pytest.mark.asyncio
    async def test_published_event_is_streamed_out(self):
        mailbox_id = 1002
        gen = _mailbox_event_source(mailbox_id)
        try:
            await asyncio.wait_for(gen.__anext__(), timeout=1)  # "ready"

            broker.publish(mailbox_id, "new_message")

            second = await asyncio.wait_for(gen.__anext__(), timeout=1)
            assert second == "event: new_message\ndata: {}\n\n"
        finally:
            await gen.aclose()

    @pytest.mark.asyncio
    async def test_unrelated_mailbox_publish_is_not_delivered(self):
        mailbox_id = 1003
        other_mailbox_id = 1004
        gen = _mailbox_event_source(mailbox_id)
        try:
            await asyncio.wait_for(gen.__anext__(), timeout=1)  # "ready"

            broker.publish(other_mailbox_id, "new_message")

            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(gen.__anext__(), timeout=0.2)
        finally:
            await gen.aclose()

    @pytest.mark.asyncio
    async def test_closing_the_generator_unsubscribes_it(self):
        mailbox_id = 1005
        gen = _mailbox_event_source(mailbox_id)
        await asyncio.wait_for(gen.__anext__(), timeout=1)  # "ready", subscribes
        await gen.aclose()

        # No subscriber left: publishing must be a no-op, not an error.
        broker.publish(mailbox_id, "new_message")


class TestIngestPublishesToTheBroker:
    """MessageService.ingest() notifies the broker on a stored message."""

    def test_ingest_publishes_for_the_recipient_mailbox(self, monkeypatch):
        address = f"stream-ingest-{uuid.uuid4().hex[:8]}@{DOMAIN}"
        password = "streampass123"
        client.post("/api/mailboxes", json={"email_address": address, "password": password})
        token = client.post(
            "/api/mailboxes/login", json={"email": address, "password": password}
        ).json()["access_token"]
        mailbox_id = client.get(
            "/api/mailboxes/me", headers={"Authorization": f"Bearer {token}"}
        ).json()["id"]

        published: list[tuple[int, str]] = []
        monkeypatch.setattr(
            "app.services.message_service.broker.publish",
            lambda mid, event: published.append((mid, event)),
        )

        import hashlib
        import hmac
        import json
        import time
        from datetime import datetime, timezone

        secret = "test-webhook-secret"
        payload = {
            "message_id": f"<{uuid.uuid4()}@worker>",
            "sender": "remetente@example.org",
            "recipient": address,
            "subject": "Nova mensagem",
            "text": "Corpo",
            "received_at": datetime.now(timezone.utc).isoformat(),
        }
        body = json.dumps(payload).encode()
        ts = str(int(time.time()))
        digest = hmac.new(secret.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()

        response = client.post(
            "/api/webhooks/inbound-email",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-DailyMail-Timestamp": ts,
                "X-DailyMail-Signature": digest,
            },
        )
        assert response.status_code == 202
        assert published == [(mailbox_id, "new_message")]
