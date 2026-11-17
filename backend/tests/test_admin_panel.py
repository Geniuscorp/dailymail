"""Tests for the admin panel's overview, system, audit, management and maintenance routes."""
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.main import app
from app.models.mailbox_session import MailboxSession
from app.models.message import Message
from app.services.admin_service import _csv_safe
from tests.conftest import TestingSessionLocal
from tests.test_admin import (  # noqa: F401  (fixtures are used by name)
    ADMIN_HASH,
    ADMIN_PASSWORD,
    ADMIN_USER,
    _admin_env,
    _admin_headers,
    WEBHOOK,
    _attachment,
    _mailbox,
    _signed,
    storage,
)

client = TestClient(app)


def _deliver(recipient: str, attachments: list[dict]) -> None:
    """Like the admin suite's helper, but every delivery has distinct content.

    Identical content for the same mailbox is (correctly) dropped as a duplicate.
    """
    payload = {
        "message_id": f"<{uuid.uuid4()}@worker>",
        "sender": "remetente@example.org",
        "recipient": recipient,
        "subject": f"Assunto {uuid.uuid4().hex[:8]}",
        "text": "Corpo",
        "html": None,
        "received_at": datetime.now(timezone.utc).isoformat(),
        "attachments": attachments,
    }
    body = json.dumps(payload).encode()
    assert client.post(WEBHOOK, content=body, headers=_signed(body)).status_code == 202


def _mailbox_id(headers: dict[str, str], address: str) -> int:
    response = client.get("/api/admin/mailboxes", params={"search": address}, headers=headers)
    assert response.status_code == 200
    return response.json()["items"][0]["id"]


def _message_id(headers: dict[str, str], mailbox_id: int) -> int:
    response = client.get("/api/admin/messages", params={"mailbox_id": mailbox_id}, headers=headers)
    return response.json()["items"][0]["id"]


class TestAuthRequired:
    @pytest.mark.parametrize(
        "method,path",
        [
            ("get", "/api/admin/overview"),
            ("get", "/api/admin/system"),
            ("get", "/api/admin/audit-logs"),
            ("get", "/api/admin/mailboxes/export"),
            ("post", "/api/admin/mailboxes/bulk-status"),
            ("get", "/api/admin/mailboxes/1"),
            ("post", "/api/admin/mailboxes/1/password"),
            ("delete", "/api/admin/mailboxes/1/sessions"),
            ("delete", "/api/admin/mailboxes/1/messages"),
            ("get", "/api/admin/messages/1"),
            ("get", "/api/admin/attachments/1/download"),
            ("get", "/api/admin/me"),
            ("post", "/api/admin/me/password"),
            ("get", "/api/admin/users"),
            ("post", "/api/admin/users"),
            ("patch", "/api/admin/users/1"),
            ("post", "/api/admin/maintenance/purge-expired"),
            ("post", "/api/admin/maintenance/purge-sessions"),
        ],
    )
    def test_rejects_anonymous_and_mailbox_tokens(self, method, path):
        assert getattr(client, method)(path).status_code in (401, 403, 422)

        _, _, mailbox_headers = _mailbox("anon")
        response = getattr(client, method)(path, headers=mailbox_headers)
        assert response.status_code == 401


class TestOverview:
    def test_counts_series_and_rankings(self, storage):
        headers = _admin_headers()
        address, _, _ = _mailbox("ov")
        _deliver(address, [])
        _deliver(address, [_attachment("a.pdf")])

        response = client.get("/api/admin/overview", params={"days": 14}, headers=headers)
        assert response.status_code == 200
        data = response.json()

        assert data["days"] == 14
        assert len(data["series"]) == 14
        assert data["series"][-1]["date"] == datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert data["mailboxes"]["total"] == (
            data["mailboxes"]["active"] + data["mailboxes"]["blocked"] + data["mailboxes"]["deleted"]
        )
        assert data["messages"]["total"] >= 2
        assert data["messages"]["last_24h"] >= 2
        assert data["attachments"]["total"] >= 1
        assert data["attachments"]["bytes"] >= len(b"%PDF")
        assert sum(point["messages"] for point in data["series"]) >= 2
        # The in-memory database is shared with every other test module.
        assert any(row["label"] == "remetente@example.org" and row["count"] >= 2 for row in data["top_senders"])
        assert any(row["label"] == "example.org" and row["count"] >= 2 for row in data["top_sender_domains"])
        assert any(row["email_address"] == address and row["count"] == 2 for row in data["busiest_mailboxes"])
        assert any(row["mime_type"] == "application/pdf" for row in data["attachment_types"])

    @pytest.mark.parametrize("days", [3, 91])
    def test_days_out_of_range_is_rejected(self, days):
        response = client.get("/api/admin/overview", params={"days": days}, headers=_admin_headers())
        assert response.status_code == 422


class TestSystem:
    def test_reports_configuration_without_leaking_secrets(self, storage):
        response = client.get("/api/admin/system", headers=_admin_headers())
        assert response.status_code == 200
        data = response.json()

        assert data["environment"] == get_settings().environment
        assert data["storage"]["configured"] is True
        assert data["inbound"]["webhook_secret_set"] is True
        assert data["uptime_seconds"] >= 0
        assert "limiter" in data["protection"]
        assert "test-webhook-secret" not in response.text
        assert ADMIN_HASH not in response.text
        assert get_settings().access_token_secret not in response.text

    def test_limiter_stats_name_the_blocked_client(self, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "rate_limit_enabled", True)
        monkeypatch.setattr(settings, "rate_limit_login_per_minute", 2)
        headers = _admin_headers()  # consumes one admin-login hit
        client.post("/api/admin/login", json={"username": "x", "password": "y"})
        assert client.post("/api/admin/login", json={"username": "x", "password": "y"}).status_code == 429

        stats = client.get("/api/admin/system", headers=headers).json()["protection"]["limiter"]
        assert stats["blocked_total"] >= 1
        blocked = stats["top_blocked"][0]
        assert blocked["scope"] == "admin-login"
        assert blocked["client"]
        assert blocked["count"] >= 1


class TestAudit:
    def test_login_and_changes_are_recorded_and_filterable(self):
        headers = _admin_headers()
        address, _, _ = _mailbox("aud")
        mailbox_id = _mailbox_id(headers, address)
        assert client.patch(
            f"/api/admin/mailboxes/{mailbox_id}", json={"status": "blocked"}, headers=headers
        ).status_code == 200

        everything = client.get("/api/admin/audit-logs", headers=headers).json()
        actions = [item["action"] for item in everything["items"]]
        assert "admin.login" in actions and "mailbox.status" in actions
        assert everything["items"][0]["admin_username"] == ADMIN_USER

        only_mailbox = client.get("/api/admin/audit-logs", params={"action": "mailbox"}, headers=headers).json()
        assert only_mailbox["total"] >= 1
        assert all(item["action"].startswith("mailbox") for item in only_mailbox["items"])

    def test_rejects_wildcard_filters(self):
        response = client.get("/api/admin/audit-logs", params={"action": "%"}, headers=_admin_headers())
        assert response.status_code == 422


class TestMailboxManagement:
    def test_detail_reports_usage(self, storage):
        headers = _admin_headers()
        address, _, _ = _mailbox("det")
        _deliver(address, [_attachment("det.pdf")])
        mailbox_id = _mailbox_id(headers, address)

        detail = client.get(f"/api/admin/mailboxes/{mailbox_id}", headers=headers).json()
        assert detail["email_address"] == address
        assert detail["message_count"] == 1
        assert detail["unread_count"] == 1
        assert detail["attachment_count"] == 1
        assert detail["storage_bytes"] > 0
        assert detail["live_sessions"] >= 1
        assert detail["last_message_at"]
        assert len(detail["recent_messages"]) == 1

    def test_unknown_mailbox_is_404(self):
        assert client.get("/api/admin/mailboxes/999999", headers=_admin_headers()).status_code == 404

    def test_password_reset_signs_the_mailbox_out(self):
        headers = _admin_headers()
        address, _, mailbox_headers = _mailbox("pwd")
        mailbox_id = _mailbox_id(headers, address)

        assert client.get("/api/mailboxes/me", headers=mailbox_headers).status_code == 200
        reset = client.post(
            f"/api/admin/mailboxes/{mailbox_id}/password",
            json={"new_password": "brand-new-pass-1"},
            headers=headers,
        )
        assert reset.status_code == 204
        assert client.get("/api/mailboxes/me", headers=mailbox_headers).status_code == 401
        assert client.post(
            "/api/mailboxes/login", json={"email": address, "password": "brand-new-pass-1"}
        ).status_code == 200

    def test_password_reset_enforces_minimum_length(self):
        headers = _admin_headers()
        address, _, _ = _mailbox("short")
        response = client.post(
            f"/api/admin/mailboxes/{_mailbox_id(headers, address)}/password",
            json={"new_password": "short"},
            headers=headers,
        )
        assert response.status_code == 422

    def test_revoking_sessions_forces_logout(self):
        headers = _admin_headers()
        address, _, mailbox_headers = _mailbox("rev")
        mailbox_id = _mailbox_id(headers, address)

        response = client.delete(f"/api/admin/mailboxes/{mailbox_id}/sessions", headers=headers)
        assert response.status_code == 200
        assert response.json()["affected"] >= 1
        assert client.get("/api/mailboxes/me", headers=mailbox_headers).status_code == 401

    def test_clearing_messages_removes_rows_and_stored_files(self, storage):
        headers = _admin_headers()
        address, _, _ = _mailbox("clr")
        _deliver(address, [_attachment("clr.pdf")])
        _deliver(address, [])
        mailbox_id = _mailbox_id(headers, address)
        assert storage.objects

        response = client.delete(f"/api/admin/mailboxes/{mailbox_id}/messages", headers=headers)
        assert response.status_code == 200
        assert response.json()["affected"] == 2
        assert client.get(f"/api/admin/mailboxes/{mailbox_id}", headers=headers).json()["message_count"] == 0
        assert not storage.objects

    def test_bulk_status_changes_every_listed_mailbox(self):
        headers = _admin_headers()
        ids = [_mailbox_id(headers, _mailbox("blk")[0]) for _ in range(3)]

        response = client.post(
            "/api/admin/mailboxes/bulk-status", json={"ids": ids + [987654], "status": "blocked"}, headers=headers
        )
        assert response.status_code == 200
        assert response.json()["affected"] == 3
        for mailbox_id in ids:
            assert client.get(f"/api/admin/mailboxes/{mailbox_id}", headers=headers).json()["status"] == "blocked"

    def test_bulk_status_validates_input(self):
        headers = _admin_headers()
        assert client.post(
            "/api/admin/mailboxes/bulk-status", json={"ids": [], "status": "blocked"}, headers=headers
        ).status_code == 422
        assert client.post(
            "/api/admin/mailboxes/bulk-status", json={"ids": [1], "status": "nope"}, headers=headers
        ).status_code == 422

    def test_csv_export_lists_mailboxes(self):
        headers = _admin_headers()
        address, _, _ = _mailbox("csv")
        response = client.get("/api/admin/mailboxes/export", params={"search": address}, headers=headers)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert "attachment" in response.headers["content-disposition"]
        lines = response.text.strip().splitlines()
        assert lines[0] == "id,email_address,status,batch_id,created_at,message_count"
        assert address in lines[1]

    @pytest.mark.parametrize("value", ["=SUM(A1)", "+1", "-1", "@cmd"])
    def test_csv_cells_that_look_like_formulas_are_neutralised(self, value):
        assert _csv_safe(value) == "'" + value
        assert _csv_safe("plain@kupay.site") == "plain@kupay.site"


class TestMessagesAndAttachments:
    def test_detail_filters_and_attachment_download(self, storage):
        headers = _admin_headers()
        address, _, _ = _mailbox("msg")
        _deliver(address, [_attachment("proof.pdf")])
        _deliver(address, [])
        mailbox_id = _mailbox_id(headers, address)

        with_files = client.get(
            "/api/admin/messages", params={"mailbox_id": mailbox_id, "has_attachments": True}, headers=headers
        ).json()
        without_files = client.get(
            "/api/admin/messages", params={"mailbox_id": mailbox_id, "has_attachments": False}, headers=headers
        ).json()
        assert with_files["total"] == 1 and without_files["total"] == 1

        message_id = with_files["items"][0]["id"]
        detail = client.get(f"/api/admin/messages/{message_id}", headers=headers).json()
        assert detail["text_body"] == "Corpo"
        assert detail["attachments"][0]["original_filename"] == "proof.pdf"

        download = client.get(
            f"/api/admin/attachments/{detail['attachments'][0]['id']}/download", headers=headers
        )
        assert download.status_code == 200
        assert download.content.startswith(b"%PDF")
        assert download.headers["x-content-type-options"] == "nosniff"
        assert download.headers["content-disposition"].startswith("attachment")

        searched = client.get("/api/admin/attachments", params={"search": "proof"}, headers=headers).json()
        assert searched["total"] >= 1
        assert all("proof" in item["original_filename"] for item in searched["items"])

    def test_unread_filter(self, storage):
        headers = _admin_headers()
        address, _, mailbox_headers = _mailbox("unr")
        _deliver(address, [])
        mailbox_id = _mailbox_id(headers, address)
        message_id = _message_id(headers, mailbox_id)

        unread = client.get("/api/admin/messages", params={"mailbox_id": mailbox_id, "unread": True}, headers=headers)
        assert unread.json()["total"] == 1
        assert client.patch(
            f"/api/messages/{message_id}/read", json={"is_read": True}, headers=mailbox_headers
        ).status_code == 200
        unread = client.get("/api/admin/messages", params={"mailbox_id": mailbox_id, "unread": True}, headers=headers)
        assert unread.json()["total"] == 0

    def test_missing_items_are_404(self, storage):
        headers = _admin_headers()
        assert client.get("/api/admin/messages/999999", headers=headers).status_code == 404
        assert client.get("/api/admin/attachments/999999/download", headers=headers).status_code == 404


class TestAdministrators:
    def test_create_list_and_duplicate(self):
        headers = _admin_headers()
        created = client.post(
            "/api/admin/users", json={"username": "second", "password": "second-admin-pass"}, headers=headers
        )
        assert created.status_code == 201
        assert created.json()["username"] == "second"
        assert "password" not in created.text

        assert client.post(
            "/api/admin/users", json={"username": "second", "password": "second-admin-pass"}, headers=headers
        ).status_code == 409
        assert {user["username"] for user in client.get("/api/admin/users", headers=headers).json()} >= {
            ADMIN_USER,
            "second",
        }

    def test_weak_credentials_are_rejected(self):
        headers = _admin_headers()
        assert client.post(
            "/api/admin/users", json={"username": "ok-name", "password": "short"}, headers=headers
        ).status_code == 422
        assert client.post(
            "/api/admin/users", json={"username": "bad name!", "password": "long-enough-pass"}, headers=headers
        ).status_code == 422

    def test_deactivated_admin_cannot_sign_in(self):
        headers = _admin_headers()
        created = client.post(
            "/api/admin/users", json={"username": "temp", "password": "temporary-pass-1"}, headers=headers
        ).json()
        assert client.post(
            "/api/admin/login", json={"username": "temp", "password": "temporary-pass-1"}
        ).status_code == 200

        patched = client.patch(f"/api/admin/users/{created['id']}", json={"status": "inactive"}, headers=headers)
        assert patched.status_code == 200
        assert client.post(
            "/api/admin/login", json={"username": "temp", "password": "temporary-pass-1"}
        ).status_code == 401

    def test_cannot_deactivate_yourself_or_the_last_admin(self):
        headers = _admin_headers()
        me = client.get("/api/admin/me", headers=headers).json()
        assert me["username"] == ADMIN_USER

        response = client.patch(f"/api/admin/users/{me['id']}", json={"status": "inactive"}, headers=headers)
        assert response.status_code == 409

    def test_change_own_password(self):
        headers = _admin_headers()
        wrong = client.post(
            "/api/admin/me/password",
            json={"current_password": "not-it", "new_password": "a-new-admin-pass"},
            headers=headers,
        )
        assert wrong.status_code == 400

        ok = client.post(
            "/api/admin/me/password",
            json={"current_password": ADMIN_PASSWORD, "new_password": "a-new-admin-pass"},
            headers=headers,
        )
        assert ok.status_code == 204
        assert client.post(
            "/api/admin/login", json={"username": ADMIN_USER, "password": ADMIN_PASSWORD}
        ).status_code == 401
        assert client.post(
            "/api/admin/login", json={"username": ADMIN_USER, "password": "a-new-admin-pass"}
        ).status_code == 200


class TestMaintenance:
    def test_purge_expired_messages_removes_only_expired_ones(self, storage):
        headers = _admin_headers()
        address, _, _ = _mailbox("prg")
        _deliver(address, [_attachment("old.pdf")])
        _deliver(address, [])
        mailbox_id = _mailbox_id(headers, address)

        with TestingSessionLocal() as db:
            oldest = db.query(Message).filter(Message.mailbox_id == mailbox_id).order_by(Message.id).first()
            oldest.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
            db.commit()

        response = client.post("/api/admin/maintenance/purge-expired", headers=headers)
        assert response.status_code == 200
        assert response.json()["affected"] >= 1
        assert client.get(f"/api/admin/mailboxes/{mailbox_id}", headers=headers).json()["message_count"] == 1
        assert not storage.objects

    def test_purge_expired_sessions(self):
        headers = _admin_headers()
        address, _, _ = _mailbox("ses")
        mailbox_id = _mailbox_id(headers, address)
        with TestingSessionLocal() as db:
            db.add(
                MailboxSession(
                    mailbox_id=mailbox_id,
                    token_hash="expired-token-hash",
                    expires_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1),
                )
            )
            db.commit()

        response = client.post("/api/admin/maintenance/purge-sessions", headers=headers)
        assert response.status_code == 200
        assert response.json()["affected"] >= 1
        with TestingSessionLocal() as db:
            assert db.query(MailboxSession).filter(MailboxSession.token_hash == "expired-token-hash").first() is None

    def test_maintenance_is_audited(self, storage):
        headers = _admin_headers()
        client.post("/api/admin/maintenance/purge-sessions", headers=headers)
        actions = [i["action"] for i in client.get("/api/admin/audit-logs", headers=headers).json()["items"]]
        assert "maintenance.purge_sessions" in actions


def test_limiter_is_reset_between_tests():
    limiter.reset()
    assert limiter.stats()["blocked_total"] == 0
