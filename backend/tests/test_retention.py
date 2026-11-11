"""Tests for message retention: hidden when expired, purged with their objects."""
import base64
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.attachment import Attachment
from app.models.message import Message
from app.storage.base import StorageError
from app.tasks.retention import purge_expired_messages
from tests.conftest import TestingSessionLocal
from tests.fakes import InMemoryStorage

client = TestClient(app)
SECRET = "test-webhook-secret"
WEBHOOK = "/api/webhooks/inbound-email"
PDF = b"%PDF-1.4\n%fake pdf body\n"


@pytest.fixture
def storage(monkeypatch):
    fake = InMemoryStorage()
    monkeypatch.setattr("app.api.webhooks.get_object_storage", lambda: fake)
    monkeypatch.setattr("app.api.attachments.get_object_storage", lambda: fake)
    return fake


@pytest.fixture(autouse=True)
def _clean_slate(storage):
    """The suite shares one database; drop expired leftovers before each test."""
    with TestingSessionLocal() as db:
        purge_expired_messages(db, storage)


def _signed(body: bytes) -> dict[str, str]:
    ts = str(int(time.time()))
    digest = hmac.new(SECRET.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
    return {"Content-Type": "application/json", "X-DailyMail-Timestamp": ts, "X-DailyMail-Signature": digest}


def _attachment(filename: str, data: bytes) -> dict:
    return {
        "filename": filename,
        "content_type": "application/pdf",
        "content_base64": base64.b64encode(data).decode(),
    }


def _deliver(recipient: str, attachments: list[dict]) -> None:
    payload = {
        "message_id": f"<{uuid.uuid4()}@worker>",
        "sender": "retencao@example.org",
        "recipient": recipient,
        "subject": "Retenção",
        "text": "Corpo",
        "html": None,
        "received_at": datetime.now(timezone.utc).isoformat(),
        "attachments": attachments,
    }
    body = json.dumps(payload).encode()
    assert client.post(WEBHOOK, content=body, headers=_signed(body)).status_code == 202


def _mailbox() -> tuple[str, dict[str, str]]:
    address = f"retencao-{uuid.uuid4().hex[:8]}@kupay.site"
    created = client.post("/api/mailboxes", json={"email_address": address, "password": "retencao-pass-123"})
    assert created.status_code == 201
    login = client.post("/api/mailboxes/login", json={"email": address, "password": "retencao-pass-123"})
    return address, {"Authorization": f"Bearer {login.json()['access_token']}"}


def _messages_for(address: str) -> list[Message]:
    with TestingSessionLocal() as db:
        return db.query(Message).filter(Message.recipient == address).all()


def _expire(address: str, days: int = 1) -> None:
    """Move the retention window of every message of the mailbox into the past."""
    with TestingSessionLocal() as db:
        for message in db.query(Message).filter(Message.recipient == address).all():
            message.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
        db.commit()


class TestExpiredMessagesAreInvisible:
    def test_expired_message_and_attachment_are_not_accessible(self, storage):
        address, headers = _mailbox()
        _deliver(address, [_attachment("doc.pdf", PDF)])

        message_id = client.get("/api/messages", headers=headers).json()[0]["id"]
        attachment_id = client.get(f"/api/messages/{message_id}", headers=headers).json()["attachments"][0]["id"]

        _expire(address)

        assert client.get("/api/messages", headers=headers).json() == []
        assert client.get(f"/api/messages/{message_id}", headers=headers).status_code == 404
        assert client.get(f"/api/attachments/{attachment_id}", headers=headers).status_code == 404
        assert client.get(f"/api/attachments/{attachment_id}/download", headers=headers).status_code == 404
        assert client.delete(f"/api/messages/{message_id}", headers=headers).status_code == 404

    def test_message_without_expiry_stays_accessible(self, storage):
        address, headers = _mailbox()
        _deliver(address, [])
        with TestingSessionLocal() as db:
            for message in db.query(Message).filter(Message.recipient == address).all():
                message.expires_at = None
            db.commit()

        assert len(client.get("/api/messages", headers=headers).json()) == 1


class TestPurge:
    def test_purge_removes_expired_message_and_its_objects(self, storage):
        address, headers = _mailbox()
        _deliver(address, [_attachment("a.pdf", PDF), _attachment("b.pdf", PDF)])
        message_id = client.get("/api/messages", headers=headers).json()[0]["id"]
        assert len(storage.objects) == 2

        _expire(address)

        with TestingSessionLocal() as db:
            purged = purge_expired_messages(db, storage)

        assert purged == 1
        assert storage.objects == {}
        with TestingSessionLocal() as db:
            assert db.get(Message, message_id) is None
            assert db.query(Attachment).filter(Attachment.message_id == message_id).count() == 0

    def test_purge_keeps_fresh_messages_and_objects(self, storage):
        address, headers = _mailbox()
        _deliver(address, [_attachment("fresh.pdf", PDF)])
        message_id = client.get("/api/messages", headers=headers).json()[0]["id"]

        with TestingSessionLocal() as db:
            purged = purge_expired_messages(db, storage)

        assert purged == 0
        assert len(storage.objects) == 1
        with TestingSessionLocal() as db:
            assert db.get(Message, message_id) is not None
        assert len(client.get("/api/messages", headers=headers).json()) == 1

    def test_purge_refuses_to_drop_attachments_without_storage(self, storage):
        address, headers = _mailbox()
        _deliver(address, [_attachment("sem-storage.pdf", PDF)])
        message_id = client.get("/api/messages", headers=headers).json()[0]["id"]
        _expire(address)

        with TestingSessionLocal() as db:
            with pytest.raises(StorageError):
                purge_expired_messages(db, storage=None)

        # The row is kept so a later run, with storage configured, can remove the object.
        with TestingSessionLocal() as db:
            assert db.get(Message, message_id) is not None
        assert len(storage.objects) == 1

    def test_purge_without_attachments_works_without_storage(self, storage):
        address, _ = _mailbox()
        _deliver(address, [])
        _expire(address)

        with TestingSessionLocal() as db:
            assert purge_expired_messages(db, storage=None) == 1
        assert _messages_for(address) == []


class TestPurgeBatching:
    def test_purge_removes_everything_across_small_batches(self, storage):
        address, headers = _mailbox()
        _deliver(address, [])
        _deliver(address, [])
        _expire(address)

        with TestingSessionLocal() as db:
            assert purge_expired_messages(db, storage, batch_size=1) == 2

        assert _messages_for(address) == []
        assert client.get("/api/messages", headers=headers).json() == []


class TestRetentionBackgroundTask:
    """The sweep also runs as a background task inside the API process
    itself (app/main.py), so it needs no separate cron job/container on a
    platform that can't easily share a volume between a service and a job.
    """

    def test_app_starts_and_stops_the_retention_loop_cleanly(self):
        # Only `with` triggers FastAPI's lifespan (startup/shutdown); this
        # confirms the background task is created and cancelled without
        # raising, without waiting out its real sleep interval.
        with TestClient(app) as test_client:
            assert test_client.get("/health").status_code == 200

    def test_run_sweep_once_wires_session_and_storage_together(self, storage, monkeypatch):
        import app.tasks.retention as retention_module

        monkeypatch.setattr(retention_module, "SessionLocal", TestingSessionLocal)
        monkeypatch.setattr(retention_module, "get_object_storage", lambda: storage)

        address, _ = _mailbox()
        _deliver(address, [_attachment("a.pdf", PDF)])
        _expire(address)

        from app.tasks.retention import run_sweep_once

        assert run_sweep_once() == 1
        assert _messages_for(address) == []
        assert storage.objects == {}
