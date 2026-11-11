"""Tests for inbound email webhook, message storage and message access."""
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app

client = TestClient(app)
SECRET = "test-webhook-secret"
WEBHOOK = "/api/webhooks/inbound-email"


def _signed_headers(body: bytes, timestamp: int | None = None) -> dict[str, str]:
    ts = str(int(time.time()) if timestamp is None else timestamp)
    digest = hmac.new(SECRET.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-DailyMail-Timestamp": ts,
        "X-DailyMail-Signature": digest,
    }


def _payload(recipient: str, **overrides) -> dict:
    data = {
        "message_id": f"<{uuid.uuid4()}@worker>",
        "sender": "Alice@Example.com",
        "recipient": recipient,
        "subject": "Olá",
        "text": "Corpo em texto",
        "html": "<p>Olá<script>alert(1)</script> <a href=\"javascript:alert(2)\">x</a></p>",
        # Fresh messages: the retention window is computed from received_at.
        "received_at": datetime.now(timezone.utc).isoformat(),
    }
    data.update(overrides)
    return data


def _deliver(payload: dict, **kwargs):
    body = json.dumps(payload).encode()
    return client.post(WEBHOOK, content=body, headers=_signed_headers(body, **kwargs))


def _create_mailbox(address: str, password: str = "mailbox-pass-123") -> str:
    created = client.post("/api/mailboxes", json={"email_address": address, "password": password})
    assert created.status_code == 201, created.text
    login = client.post("/api/mailboxes/login", json={"email": address, "password": password})
    assert login.status_code == 200
    return login.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestWebhookDelivery:
    def test_valid_delivery_is_stored_and_visible_to_mailbox(self):
        address = f"recv-{uuid.uuid4().hex[:8]}@kupay.site"
        token = _create_mailbox(address)

        response = _deliver(_payload(address))
        assert response.status_code == 202
        assert response.json() == {"status": "stored"}

        listing = client.get("/api/messages", headers=_auth(token))
        assert listing.status_code == 200
        items = listing.json()
        assert len(items) == 1
        assert items[0]["sender"] == "alice@example.com"
        assert items[0]["subject"] == "Olá"
        assert items[0]["is_read"] is False
        assert items[0]["expires_at"] is not None

    def test_duplicate_message_id_is_not_stored_twice(self):
        address = f"dup-{uuid.uuid4().hex[:8]}@kupay.site"
        token = _create_mailbox(address)
        payload = _payload(address)

        assert _deliver(payload).json() == {"status": "stored"}
        assert _deliver(payload).json() == {"status": "duplicate"}

        assert len(client.get("/api/messages", headers=_auth(token)).json()) == 1

    def test_same_message_id_to_another_mailbox_is_still_delivered(self):
        """A Message-ID is unique per sender, not across the service. A sender
        that reuses one (or one message fanned out to several recipients) must
        not stop every other mailbox from receiving its mail."""
        first = f"fan1-{uuid.uuid4().hex[:8]}@kupay.site"
        second = f"fan2-{uuid.uuid4().hex[:8]}@kupay.site"
        token_first = _create_mailbox(first)
        token_second = _create_mailbox(second)
        shared_id = f"<{uuid.uuid4()}@sender.example>"

        assert _deliver(_payload(first, message_id=shared_id)).json() == {"status": "stored"}
        assert _deliver(_payload(second, message_id=shared_id)).json() == {"status": "stored"}

        assert len(client.get("/api/messages", headers=_auth(token_first)).json()) == 1
        assert len(client.get("/api/messages", headers=_auth(token_second)).json()) == 1

    def test_unknown_recipient_is_ignored(self):
        response = _deliver(_payload(f"nobody-{uuid.uuid4().hex[:8]}@kupay.site"))
        assert response.status_code == 202
        assert response.json() == {"status": "ignored"}

    def test_missing_signature_is_rejected(self):
        body = json.dumps(_payload("x@kupay.site")).encode()
        response = client.post(WEBHOOK, content=body, headers={"Content-Type": "application/json"})
        assert response.status_code == 401

    def test_wrong_signature_is_rejected(self):
        body = json.dumps(_payload("x@kupay.site")).encode()
        headers = _signed_headers(body)
        headers["X-DailyMail-Signature"] = "0" * 64
        assert client.post(WEBHOOK, content=body, headers=headers).status_code == 401

    def test_tampered_body_is_rejected(self):
        address = f"tamper-{uuid.uuid4().hex[:8]}@kupay.site"
        _create_mailbox(address)
        body = json.dumps(_payload(address)).encode()
        headers = _signed_headers(body)
        tampered = body.replace(b"Corpo em texto", b"Outro corpo")
        assert client.post(WEBHOOK, content=tampered, headers=headers).status_code == 401

    def test_stale_timestamp_is_rejected(self):
        body = json.dumps(_payload("x@kupay.site")).encode()
        headers = _signed_headers(body, timestamp=int(time.time()) - 3600)
        assert client.post(WEBHOOK, content=body, headers=headers).status_code == 401

    def test_signed_but_invalid_json_is_rejected(self):
        body = b"not json"
        assert client.post(WEBHOOK, content=body, headers=_signed_headers(body)).status_code == 401

    def test_oversized_payload_is_rejected(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "max_inbound_payload_mb", 1)
        body = b"{" + b" " * (2 * 1024 * 1024) + b"}"
        response = client.post(WEBHOOK, content=body, headers=_signed_headers(body))
        assert response.status_code == 413

    def test_html_body_is_sanitised(self):
        address = f"html-{uuid.uuid4().hex[:8]}@kupay.site"
        token = _create_mailbox(address)
        _deliver(_payload(address))

        message_id = client.get("/api/messages", headers=_auth(token)).json()[0]["id"]
        detail = client.get(f"/api/messages/{message_id}", headers=_auth(token)).json()

        assert "<script" not in detail["html_body_sanitized"]
        assert "javascript:" not in detail["html_body_sanitized"]
        assert "Olá" in detail["html_body_sanitized"]
        assert detail["text_body"] == "Corpo em texto"


class TestMessageAccess:
    def test_message_is_not_visible_to_other_mailbox(self):
        owner_address = f"owner-{uuid.uuid4().hex[:8]}@kupay.site"
        other_address = f"other-{uuid.uuid4().hex[:8]}@kupay.site"
        owner_token = _create_mailbox(owner_address)
        other_token = _create_mailbox(other_address)

        _deliver(_payload(owner_address))
        message_id = client.get("/api/messages", headers=_auth(owner_token)).json()[0]["id"]

        assert client.get("/api/messages", headers=_auth(other_token)).json() == []
        assert client.get(f"/api/messages/{message_id}", headers=_auth(other_token)).status_code == 404
        assert client.patch(
            f"/api/messages/{message_id}/read", json={"is_read": True}, headers=_auth(other_token)
        ).status_code == 404
        assert client.delete(f"/api/messages/{message_id}", headers=_auth(other_token)).status_code == 404

    def test_messages_require_authentication(self):
        assert client.get("/api/messages").status_code == 403

    def test_mark_read_and_delete(self):
        address = f"state-{uuid.uuid4().hex[:8]}@kupay.site"
        token = _create_mailbox(address)
        _deliver(_payload(address))
        message_id = client.get("/api/messages", headers=_auth(token)).json()[0]["id"]

        updated = client.patch(
            f"/api/messages/{message_id}/read", json={"is_read": True}, headers=_auth(token)
        )
        assert updated.status_code == 200
        assert updated.json()["is_read"] is True

        assert client.delete(f"/api/messages/{message_id}", headers=_auth(token)).status_code == 204
        assert client.get(f"/api/messages/{message_id}", headers=_auth(token)).status_code == 404
