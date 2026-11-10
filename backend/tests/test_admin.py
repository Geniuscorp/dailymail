"""Tests for the admin API: authentication, scoping, management and audit."""
import base64
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.core.security import hash_password
from app.main import app
from app.models.admin_audit_log import AdminAuditLog
from app.models.admin_user import AdminUser
from app.storage import StorageNotConfiguredError
from tests.conftest import TestingSessionLocal
from tests.fakes import InMemoryStorage

client = TestClient(app)
SECRET = "test-webhook-secret"
WEBHOOK = "/api/webhooks/inbound-email"
ADMIN_USER = "admin"
ADMIN_PASSWORD = "admin-pass-123"
ADMIN_HASH = hash_password(ADMIN_PASSWORD)
PDF = b"%PDF-1.4\n%fake pdf body\n"


@pytest.fixture(autouse=True)
def _admin_env(monkeypatch):
    """Configure env-based admin bootstrap and start every test with no admins."""
    settings = get_settings()
    monkeypatch.setattr(settings, "admin_username", ADMIN_USER)
    monkeypatch.setattr(settings, "admin_password_hash", ADMIN_HASH)
    limiter.reset()
    with TestingSessionLocal() as db:
        db.query(AdminAuditLog).delete()
        db.query(AdminUser).delete()
        db.commit()
    yield
    limiter.reset()


@pytest.fixture
def storage(monkeypatch):
    fake = InMemoryStorage()
    monkeypatch.setattr("app.api.webhooks.get_object_storage", lambda: fake)
    monkeypatch.setattr("app.api.attachments.get_object_storage", lambda: fake)
    monkeypatch.setattr("app.api.admin.get_object_storage", lambda: fake)
    return fake


def _login(password: str = ADMIN_PASSWORD):
    return client.post(
        "/api/admin/login", json={"username": ADMIN_USER, "password": password}
    )


def _admin_headers() -> dict[str, str]:
    response = _login()
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _mailbox(prefix: str = "adm") -> tuple[str, str, dict[str, str]]:
    address = f"{prefix}-{uuid.uuid4().hex[:8]}@kupay.site"
    password = "mailbox-pass-123"
    assert client.post(
        "/api/mailboxes", json={"email_address": address, "password": password}
    ).status_code == 201
    login = client.post("/api/mailboxes/login", json={"email": address, "password": password})
    assert login.status_code == 200
    return address, password, {"Authorization": f"Bearer {login.json()['access_token']}"}


def _signed(body: bytes) -> dict[str, str]:
    ts = str(int(time.time()))
    digest = hmac.new(SECRET.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
    return {"Content-Type": "application/json", "X-DailyMail-Timestamp": ts, "X-DailyMail-Signature": digest}


def _deliver(recipient: str, attachments: list[dict]) -> None:
    payload = {
        "message_id": f"<{uuid.uuid4()}@worker>",
        "sender": "remetente@example.org",
        "recipient": recipient,
        "subject": "Assunto admin",
        "text": "Corpo",
        "html": None,
        "received_at": datetime.now(timezone.utc).isoformat(),
        "attachments": attachments,
    }
    body = json.dumps(payload).encode()
    assert client.post(WEBHOOK, content=body, headers=_signed(body)).status_code == 202


def _attachment(filename: str, data: bytes = PDF) -> dict:
    return {
        "filename": filename,
        "content_type": "application/pdf",
        "content_base64": base64.b64encode(data).decode(),
    }


def _admin_messages(headers: dict[str, str], search: str) -> list[dict]:
    response = client.get("/api/admin/messages", params={"search": search}, headers=headers)
    assert response.status_code == 200
    return response.json()["items"]


def _raise_not_configured():
    raise StorageNotConfiguredError("not configured")


class TestAdminAuthentication:
    def test_login_returns_token_and_dashboard(self):
        login = _login()
        assert login.status_code == 200
        body = login.json()
        assert body["token_type"] == "bearer"
        assert body["expires_in"] > 0

        dashboard = client.get(
            "/api/admin/dashboard",
            headers={"Authorization": f"Bearer {body['access_token']}"},
        )
        assert dashboard.status_code == 200
        data = dashboard.json()
        assert set(data) == {
            "total_mailboxes",
            "active_mailboxes",
            "total_messages",
            "total_attachments",
            "storage_used_mb",
            "expiring_soon",
        }
        assert data["total_mailboxes"] >= 0

    def test_wrong_password_is_rejected(self):
        assert _login("wrong-password").status_code == 401

    def test_unknown_username_is_rejected(self):
        response = client.post(
            "/api/admin/login", json={"username": "intruder", "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 401

    def test_unconfigured_admin_returns_503(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "admin_password_hash", "")
        response = _login()
        assert response.status_code == 503

    def test_dashboard_requires_authentication(self):
        assert client.get("/api/admin/dashboard").status_code == 403

    def test_mailbox_token_cannot_use_admin_api(self):
        _, _, mailbox_headers = _mailbox("scope")
        response = client.get("/api/admin/dashboard", headers=mailbox_headers)
        assert response.status_code == 401

    def test_admin_token_cannot_use_mailbox_api(self):
        response = client.get("/api/mailboxes/me", headers=_admin_headers())
        assert response.status_code == 401


class TestAdminMailboxes:
    def test_search_status_filter_and_block(self):
        address, password, _ = _mailbox("blocked")
        headers = _admin_headers()

        listing = client.get("/api/admin/mailboxes", params={"search": address}, headers=headers)
        assert listing.status_code == 200
        items = listing.json()["items"]
        assert [item["email_address"] for item in items] == [address]
        assert items[0]["message_count"] == 0

        mailbox_id = items[0]["id"]
        patched = client.patch(
            f"/api/admin/mailboxes/{mailbox_id}", json={"status": "blocked"}, headers=headers
        )
        assert patched.status_code == 200
        assert patched.json()["status"] == "blocked"

        assert client.post(
            "/api/mailboxes/login", json={"email": address, "password": password}
        ).status_code == 401

        filtered = client.get(
            "/api/admin/mailboxes", params={"search": address, "status": "blocked"}, headers=headers
        )
        assert filtered.json()["total"] == 1

    def test_delete_is_soft_and_account_stops_working(self):
        address, password, _ = _mailbox("removed")
        headers = _admin_headers()
        mailbox_id = client.get(
            "/api/admin/mailboxes", params={"search": address}, headers=headers
        ).json()["items"][0]["id"]

        assert client.delete(f"/api/admin/mailboxes/{mailbox_id}", headers=headers).status_code == 204
        assert client.post(
            "/api/mailboxes/login", json={"email": address, "password": password}
        ).status_code == 401

        item = client.get(
            "/api/admin/mailboxes", params={"search": address}, headers=headers
        ).json()["items"][0]
        assert item["status"] == "deleted"

    def test_status_response_reports_the_real_message_count(self, storage):
        address, _, _ = _mailbox("count")
        _deliver(address, [_attachment("conta.pdf")])
        headers = _admin_headers()
        mailbox_id = client.get(
            "/api/admin/mailboxes", params={"search": address}, headers=headers
        ).json()["items"][0]["id"]

        patched = client.patch(
            f"/api/admin/mailboxes/{mailbox_id}", json={"status": "active"}, headers=headers
        )
        assert patched.status_code == 200
        assert patched.json()["message_count"] == 1

    def test_status_change_is_audited(self):
        address, _, _ = _mailbox("audited")
        headers = _admin_headers()
        mailbox_id = client.get(
            "/api/admin/mailboxes", params={"search": address}, headers=headers
        ).json()["items"][0]["id"]

        client.patch(f"/api/admin/mailboxes/{mailbox_id}", json={"status": "active"}, headers=headers)

        with TestingSessionLocal() as db:
            actions = [row.action for row in db.query(AdminAuditLog).all()]
        assert "mailbox.status" in actions

    def test_unknown_mailbox_returns_404(self):
        headers = _admin_headers()
        assert client.patch(
            "/api/admin/mailboxes/999999", json={"status": "blocked"}, headers=headers
        ).status_code == 404
        assert client.delete("/api/admin/mailboxes/999999", headers=headers).status_code == 404


class TestAdminBatches:
    def test_reset_batch_password_updates_mailboxes(self):
        password = "batch-pass-123"
        created = client.post(
            "/api/mailboxes/batch",
            json={"quantity": 1, "password": password, "generation_type": "random"},
        )
        assert created.status_code == 201
        address = created.json()["mailboxes"][0]
        batch_id = created.json()["id"]

        headers = _admin_headers()
        listed = client.get("/api/admin/batches", headers=headers)
        assert listed.status_code == 200
        assert any(item["id"] == batch_id for item in listed.json()["items"])

        reset = client.patch(
            f"/api/admin/batches/{batch_id}/password",
            json={"new_password": "new-batch-pass-123"},
            headers=headers,
        )
        assert reset.status_code == 204

        assert client.post(
            "/api/mailboxes/login", json={"email": address, "password": "new-batch-pass-123"}
        ).status_code == 200

    def test_unknown_batch_returns_404(self):
        headers = _admin_headers()
        assert client.patch(
            "/api/admin/batches/999999/password",
            json={"new_password": "whatever-pass-123"},
            headers=headers,
        ).status_code == 404


class TestAdminMessages:
    def test_search_and_delete_removes_stored_objects(self, storage):
        address, _, _ = _mailbox("msg-admin")
        _deliver(address, [_attachment("a.pdf"), _attachment("b.pdf")])
        headers = _admin_headers()

        items = _admin_messages(headers, address)
        assert len(items) == 1
        assert items[0]["attachment_count"] == 2

        assert client.delete(
            f"/api/admin/messages/{items[0]['id']}", headers=headers
        ).status_code == 204
        assert storage.objects == {}
        assert _admin_messages(headers, address) == []

    def test_delete_without_storage_is_refused(self, storage, monkeypatch):
        address, _, _ = _mailbox("msg-nostorage")
        _deliver(address, [_attachment("locked.pdf")])
        headers = _admin_headers()
        message_id = _admin_messages(headers, address)[0]["id"]

        monkeypatch.setattr("app.api.admin.get_object_storage", _raise_not_configured)
        assert client.delete(f"/api/admin/messages/{message_id}", headers=headers).status_code == 503
        assert len(storage.objects) == 1
        assert len(_admin_messages(headers, address)) == 1

    def test_list_and_delete_attachments(self, storage):
        address, _, _ = _mailbox("att-admin")
        _deliver(address, [_attachment("conta.pdf")])
        headers = _admin_headers()
        message_id = _admin_messages(headers, address)[0]["id"]

        listed = client.get(
            "/api/admin/attachments", params={"message_id": message_id}, headers=headers
        )
        assert listed.status_code == 200
        items = listed.json()["items"]
        assert [item["original_filename"] for item in items] == ["conta.pdf"]

        assert client.delete(
            f"/api/admin/attachments/{items[0]['id']}", headers=headers
        ).status_code == 204
        assert storage.objects == {}
