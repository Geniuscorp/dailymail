"""Tests for inbound attachments: policy, storage, download authorisation and cleanup."""
import base64
import hashlib
import hmac
import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from tests.fakes import InMemoryStorage

client = TestClient(app)
SECRET = "test-webhook-secret"
WEBHOOK = "/api/webhooks/inbound-email"
PDF = b"%PDF-1.4\n%fake pdf body\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
ZIP = b"PK\x03\x04" + b"\x00" * 16


@pytest.fixture
def storage(monkeypatch):
    fake = InMemoryStorage()
    monkeypatch.setattr("app.api.webhooks.get_object_storage", lambda: fake)
    monkeypatch.setattr("app.api.attachments.get_object_storage", lambda: fake)
    return fake


def _signed(body: bytes) -> dict[str, str]:
    ts = str(int(time.time()))
    digest = hmac.new(SECRET.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
    return {"Content-Type": "application/json", "X-DailyMail-Timestamp": ts, "X-DailyMail-Signature": digest}


def _attachment(filename, data, content_type="application/octet-stream"):
    return {"filename": filename, "content_type": content_type, "content_base64": base64.b64encode(data).decode()}


def _deliver(recipient, attachments, message_id=None):
    payload = {
        "message_id": message_id or f"<{uuid.uuid4()}@worker>",
        "sender": "envia@example.org",
        "recipient": recipient,
        "subject": "Com anexos",
        "text": "Veja os anexos",
        "html": None,
        "received_at": "2026-01-10T12:00:00Z",
        "attachments": attachments,
    }
    body = json.dumps(payload).encode()
    return client.post(WEBHOOK, content=body, headers=_signed(body))


def _mailbox(prefix="anexos"):
    address = f"{prefix}-{uuid.uuid4().hex[:8]}@kupay.site"
    created = client.post("/api/mailboxes", json={"email_address": address, "password": "anexos-pass-123"})
    assert created.status_code == 201
    token = client.post("/api/mailboxes/login", json={"email": address, "password": "anexos-pass-123"}).json()[
        "access_token"
    ]
    return address, {"Authorization": f"Bearer {token}"}


def _first_message(headers):
    return client.get("/api/messages", headers=headers).json()[0]


class TestIngestion:
    def test_allowed_attachments_are_stored_outside_the_database(self, storage):
        address, headers = _mailbox()
        response = _deliver(address, [_attachment("Relatório.pdf", PDF), _attachment("foto.PNG", PNG)])
        assert response.json() == {"status": "stored"}

        summary = _first_message(headers)
        assert summary["attachment_count"] == 2

        detail = client.get(f"/api/messages/{summary['id']}", headers=headers).json()
        names = {a["original_filename"]: a for a in detail["attachments"]}
        assert set(names) == {"Relatório.pdf", "foto.PNG"}
        assert names["Relatório.pdf"]["mime_type"] == "application/pdf"
        assert names["foto.PNG"]["mime_type"] == "image/png"
        assert names["Relatório.pdf"]["file_size"] == len(PDF)

        assert len(storage.objects) == 2
        for key in storage.objects:
            assert "Relatório" not in key and "foto" not in key

    def test_disallowed_extension_is_dropped_but_message_is_kept(self, storage):
        address, headers = _mailbox()
        _deliver(address, [_attachment("programa.exe", b"MZ\x90\x00"), _attachment("ok.pdf", PDF)])
        detail = client.get(f"/api/messages/{_first_message(headers)['id']}", headers=headers).json()
        assert [a["original_filename"] for a in detail["attachments"]] == ["ok.pdf"]
        assert len(storage.objects) == 1

    def test_content_must_match_the_claimed_format(self, storage):
        address, headers = _mailbox()
        _deliver(address, [_attachment("falso.pdf", b"<html>not a pdf</html>")])
        assert _first_message(headers)["attachment_count"] == 0
        assert storage.objects == {}

    def test_path_components_in_filename_are_removed(self, storage):
        address, headers = _mailbox()
        _deliver(address, [_attachment("../../etc/relatorio.pdf", PDF)])
        detail = client.get(f"/api/messages/{_first_message(headers)['id']}", headers=headers).json()
        assert detail["attachments"][0]["original_filename"] == "relatorio.pdf"

    def test_oversized_attachment_is_dropped(self, storage, monkeypatch):
        monkeypatch.setattr(get_settings(), "max_attachment_size_mb", 0.001)
        address, headers = _mailbox()
        _deliver(address, [_attachment("grande.pdf", PDF + b"x" * 2000)])
        assert _first_message(headers)["attachment_count"] == 0

    def test_per_message_limit_keeps_only_the_first_attachments(self, storage, monkeypatch):
        monkeypatch.setattr(get_settings(), "max_attachments_per_message", 2)
        address, headers = _mailbox()
        _deliver(address, [_attachment("a.pdf", PDF), _attachment("b.pdf", PDF), _attachment("c.pdf", PDF)])
        assert _first_message(headers)["attachment_count"] == 2

    def test_malformed_base64_rejects_the_delivery(self, storage):
        address, headers = _mailbox()
        payload = {
            "message_id": f"<{uuid.uuid4()}@worker>",
            "sender": "x@example.org",
            "recipient": address,
            "attachments": [{"filename": "a.pdf", "content_base64": "!!!not-base64!!!"}],
        }
        body = json.dumps(payload).encode()
        assert client.post(WEBHOOK, content=body, headers=_signed(body)).status_code == 401
        assert client.get("/api/messages", headers=headers).json() == []

    def test_storage_outage_fails_delivery_and_keeps_nothing(self, storage):
        storage.fail_puts_after = 1
        address, headers = _mailbox()
        response = _deliver(address, [_attachment("a.pdf", PDF), _attachment("b.pdf", PDF)])
        assert response.status_code == 503
        assert client.get("/api/messages", headers=headers).json() == []
        assert storage.objects == {}

    def test_attachments_without_configured_storage_are_refused(self, monkeypatch):
        monkeypatch.setattr("app.api.webhooks.get_object_storage", _raise_not_configured)
        address, headers = _mailbox()
        assert _deliver(address, [_attachment("a.pdf", PDF)]).status_code == 503
        assert client.get("/api/messages", headers=headers).json() == []

    def test_text_only_mail_works_without_storage(self, monkeypatch):
        monkeypatch.setattr("app.api.webhooks.get_object_storage", _raise_not_configured)
        address, headers = _mailbox()
        assert _deliver(address, []).json() == {"status": "stored"}
        assert _first_message(headers)["attachment_count"] == 0

    def test_duplicate_delivery_does_not_store_objects_again(self, storage):
        address, _ = _mailbox()
        message_id = f"<{uuid.uuid4()}@worker>"
        _deliver(address, [_attachment("a.pdf", PDF)], message_id=message_id)
        assert _deliver(address, [_attachment("a.pdf", PDF)], message_id=message_id).json() == {"status": "duplicate"}
        assert len(storage.objects) == 1


def _raise_not_configured():
    from app.storage import StorageNotConfiguredError

    raise StorageNotConfiguredError("not configured")


class TestDownloads:
    def test_owner_downloads_original_bytes_with_safe_headers(self, storage):
        address, headers = _mailbox()
        _deliver(address, [_attachment("doc.pdf", PDF)])
        detail = client.get(f"/api/messages/{_first_message(headers)['id']}", headers=headers).json()
        attachment_id = detail["attachments"][0]["id"]

        response = client.get(f"/api/attachments/{attachment_id}/download", headers=headers)
        assert response.status_code == 200
        assert response.content == PDF
        assert response.headers["content-type"] == "application/pdf"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["cache-control"] == "private, no-store"
        assert response.headers["content-disposition"].startswith("attachment;")
        assert "content-security-policy" not in response.headers

    def test_inline_view_is_sandboxed_for_viewable_formats(self, storage):
        address, headers = _mailbox()
        _deliver(address, [_attachment("doc.pdf", PDF)])
        attachment_id = client.get(f"/api/messages/{_first_message(headers)['id']}", headers=headers).json()[
            "attachments"
        ][0]["id"]

        response = client.get(f"/api/attachments/{attachment_id}/download?inline=true", headers=headers)
        assert response.headers["content-disposition"].startswith("inline;")
        assert response.headers["content-security-policy"] == "sandbox; default-src 'none'"

    def test_inline_is_ignored_for_archives(self, storage):
        address, headers = _mailbox()
        _deliver(address, [_attachment("pacote.zip", ZIP)])
        attachment_id = client.get(f"/api/messages/{_first_message(headers)['id']}", headers=headers).json()[
            "attachments"
        ][0]["id"]

        response = client.get(f"/api/attachments/{attachment_id}/download?inline=true", headers=headers)
        assert response.headers["content-disposition"].startswith("attachment;")

    def test_other_mailbox_gets_not_found(self, storage):
        owner, owner_headers = _mailbox("dono")
        _, other_headers = _mailbox("outra")
        _deliver(owner, [_attachment("privado.pdf", PDF)])
        owner_message = _first_message(owner_headers)
        detail = client.get(f"/api/messages/{owner_message['id']}", headers=owner_headers).json()
        attachment_id = detail["attachments"][0]["id"]

        assert client.get(f"/api/attachments/{attachment_id}", headers=other_headers).status_code == 404
        assert client.get(f"/api/attachments/{attachment_id}/download", headers=other_headers).status_code == 404

    def test_download_requires_authentication(self, storage):
        assert client.get("/api/attachments/1/download").status_code == 403


class TestCleanup:
    def test_deleting_a_message_removes_its_objects(self, storage):
        address, headers = _mailbox()
        _deliver(address, [_attachment("a.pdf", PDF), _attachment("b.png", PNG)])
        message_id = _first_message(headers)["id"]
        assert len(storage.objects) == 2

        assert client.delete(f"/api/messages/{message_id}", headers=headers).status_code == 204
        assert storage.objects == {}
