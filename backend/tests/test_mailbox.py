"""Tests for mailbox operations."""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.models.mailbox import Mailbox
from app.models.message import Message
from tests.conftest import TestingSessionLocal

client = TestClient(app)
DOMAIN = get_settings().domain


class TestMailboxCreation:
    """Test mailbox creation."""

    def test_create_single_mailbox(self):
        """Test creating a single mailbox."""
        response = client.post(
            "/api/mailboxes",
            json={
                "email_address": "test@kupay.site",
                "password": "securepassword123",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["email_address"] == "test@kupay.site"
        assert data["status"] == "active"
        assert "id" in data

    def test_create_mailbox_duplicate(self):
        """Test creating duplicate mailbox fails."""
        # Create first
        client.post(
            "/api/mailboxes",
            json={
                "email_address": "duplicate@kupay.site",
                "password": "password123",
            },
        )
        # Try duplicate
        response = client.post(
            "/api/mailboxes",
            json={
                "email_address": "duplicate@kupay.site",
                "password": "password123",
            },
        )
        assert response.status_code == 409

    def test_create_mailbox_weak_password(self):
        """Test weak password is rejected."""
        response = client.post(
            "/api/mailboxes",
            json={
                "email_address": "weak@kupay.site",
                "password": "short",
            },
        )
        assert response.status_code == 422  # Validation error


class TestMailboxBatch:
    """Test batch mailbox creation."""

    def test_create_batch_random(self):
        """Test creating batch with random addresses."""
        response = client.post(
            "/api/mailboxes/batch",
            json={
                "quantity": 5,
                "password": "batchpassword123",
                "generation_type": "random",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["quantity"] == 5
        assert len(data["mailboxes"]) == 5
        assert data["generation_type"] == "random"

    def test_create_batch_custom(self):
        """Test creating batch with custom prefix."""
        response = client.post(
            "/api/mailboxes/batch",
            json={
                "quantity": 3,
                "password": "batchpassword123",
                "generation_type": "random",
                "prefix": "test",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert len(data["mailboxes"]) == 3
        # Check addresses start with prefix
        for addr in data["mailboxes"]:
            assert addr.startswith("test")


class TestMailboxAuthentication:
    """Test mailbox login and authentication."""

    def test_login_success(self):
        """Test successful login."""
        # Create mailbox
        client.post(
            "/api/mailboxes",
            json={
                "email_address": "login@kupay.site",
                "password": "loginpassword123",
            },
        )
        # Login
        response = client.post(
            "/api/mailboxes/login",
            json={
                "email": "login@kupay.site",
                "password": "loginpassword123",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["token_type"] == "bearer"
        assert "access_token" in data
        assert "expires_in" in data

    def test_login_invalid_password(self):
        """Test login with invalid password."""
        # Create mailbox
        client.post(
            "/api/mailboxes",
            json={
                "email_address": "invalid@kupay.site",
                "password": "correctpassword123",
            },
        )
        # Try wrong password
        response = client.post(
            "/api/mailboxes/login",
            json={
                "email": "invalid@kupay.site",
                "password": "wrongpassword123",
            },
        )
        assert response.status_code == 401

    def test_login_nonexistent(self):
        """Test login for non-existent mailbox."""
        response = client.post(
            "/api/mailboxes/login",
            json={
                "email": "nonexistent@kupay.site",
                "password": "anypassword123",
            },
        )
        assert response.status_code == 401

    def test_get_current_mailbox(self):
        """Test getting current mailbox info."""
        # Create and login
        client.post(
            "/api/mailboxes",
            json={
                "email_address": "current@kupay.site",
                "password": "currentpassword123",
            },
        )
        login_response = client.post(
            "/api/mailboxes/login",
            json={
                "email": "current@kupay.site",
                "password": "currentpassword123",
            },
        )
        token = login_response.json()["access_token"]

        # Get current mailbox
        response = client.get(
            "/api/mailboxes/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email_address"] == "current@kupay.site"

    def test_unauthorized_access(self):
        """Test accessing protected route without token."""
        response = client.get("/api/mailboxes/me")
        assert response.status_code == 403  # No credentials


class TestPasswordUpdate:
    """Test password update."""

    def test_update_password_success(self):
        """Test successful password update."""
        # Create and login
        client.post(
            "/api/mailboxes",
            json={
                "email_address": "updatepass@kupay.site",
                "password": "oldpassword123",
            },
        )
        login_response = client.post(
            "/api/mailboxes/login",
            json={
                "email": "updatepass@kupay.site",
                "password": "oldpassword123",
            },
        )
        token = login_response.json()["access_token"]

        # Update password
        response = client.patch(
            "/api/mailboxes/me/password",
            json={
                "current_password": "oldpassword123",
                "new_password": "newpassword123",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200

        # Try login with new password
        login_response = client.post(
            "/api/mailboxes/login",
            json={
                "email": "updatepass@kupay.site",
                "password": "newpassword123",
            },
        )
        assert login_response.status_code == 200

    def test_update_password_wrong_current(self):
        """Test password update with wrong current password."""
        # Create and login
        client.post(
            "/api/mailboxes",
            json={
                "email_address": "wrongcurrent@kupay.site",
                "password": "correct123",
            },
        )
        login_response = client.post(
            "/api/mailboxes/login",
            json={
                "email": "wrongcurrent@kupay.site",
                "password": "correct123",
            },
        )
        token = login_response.json()["access_token"]

        # Try update with wrong current password
        response = client.patch(
            "/api/mailboxes/me/password",
            json={
                "current_password": "wrong123",
                "new_password": "newpassword123",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401


class TestPersistentSessions:
    """Sessions are opaque and DB-backed: revocable, and outliving a tab close."""

    def _create_and_login(self, address: str, password: str) -> str:
        client.post("/api/mailboxes", json={"email_address": address, "password": password})
        login = client.post("/api/mailboxes/login", json={"email": address, "password": password})
        return login.json()["access_token"]

    def test_logout_revokes_only_the_current_session(self):
        address = f"logout-{uuid.uuid4().hex[:8]}@{DOMAIN}"
        password = "logoutpass123"
        token_a = self._create_and_login(address, password)
        login_b = client.post("/api/mailboxes/login", json={"email": address, "password": password})
        token_b = login_b.json()["access_token"]

        assert token_a != token_b

        logout = client.post("/api/mailboxes/logout", headers={"Authorization": f"Bearer {token_a}"})
        assert logout.status_code == 204

        revoked = client.get("/api/mailboxes/me", headers={"Authorization": f"Bearer {token_a}"})
        assert revoked.status_code == 401

        still_valid = client.get("/api/mailboxes/me", headers={"Authorization": f"Bearer {token_b}"})
        assert still_valid.status_code == 200

    def test_password_change_revokes_other_sessions_but_keeps_this_one(self):
        address = f"revoke-{uuid.uuid4().hex[:8]}@{DOMAIN}"
        password = "oldpassword123"
        token_other_device = self._create_and_login(address, password)
        login_this_device = client.post("/api/mailboxes/login", json={"email": address, "password": password})
        token_this_device = login_this_device.json()["access_token"]

        update = client.patch(
            "/api/mailboxes/me/password",
            json={"current_password": password, "new_password": "newpassword456"},
            headers={"Authorization": f"Bearer {token_this_device}"},
        )
        assert update.status_code == 200

        other_device = client.get("/api/mailboxes/me", headers={"Authorization": f"Bearer {token_other_device}"})
        assert other_device.status_code == 401

        this_device = client.get("/api/mailboxes/me", headers={"Authorization": f"Bearer {token_this_device}"})
        assert this_device.status_code == 200

    def test_deleting_a_mailbox_revokes_its_sessions(self):
        address = f"delete-session-{uuid.uuid4().hex[:8]}@{DOMAIN}"
        password = "deletesession123"
        token = self._create_and_login(address, password)

        assert client.delete("/api/mailboxes/me", headers={"Authorization": f"Bearer {token}"}).status_code == 204
        assert client.get("/api/mailboxes/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401

    def test_logout_requires_authentication(self):
        assert client.post("/api/mailboxes/logout").status_code == 403

    def test_garbage_token_is_rejected(self):
        response = client.get("/api/mailboxes/me", headers={"Authorization": "Bearer not-a-real-token"})
        assert response.status_code == 401


class TestAddressDomainValidation:
    """Addresses must belong to the configured domain, including generated batches."""

    def test_batch_random_addresses_include_domain(self):
        response = client.post(
            "/api/mailboxes/batch",
            json={"quantity": 4, "password": "batchpassword123", "generation_type": "random"},
        )
        assert response.status_code == 201
        addresses = response.json()["mailboxes"]
        assert len(addresses) == 4
        assert len(set(addresses)) == 4
        for address in addresses:
            assert address.endswith(f"@{DOMAIN}")

    def test_batch_prefix_addresses_include_domain(self):
        response = client.post(
            "/api/mailboxes/batch",
            json={
                "quantity": 2,
                "password": "batchpassword123",
                "generation_type": "random",
                "prefix": "team",
            },
        )
        assert response.status_code == 201
        addresses = response.json()["mailboxes"]
        assert addresses == [f"team001@{DOMAIN}", f"team002@{DOMAIN}"]

    def test_batch_custom_addresses_are_accepted(self):
        response = client.post(
            "/api/mailboxes/batch",
            json={
                "quantity": 2,
                "password": "batchpassword123",
                "generation_type": "custom",
                "custom_addresses": [f"custom-one@{DOMAIN}", f"custom-two@{DOMAIN}"],
            },
        )
        assert response.status_code == 201
        assert response.json()["mailboxes"] == [f"custom-one@{DOMAIN}", f"custom-two@{DOMAIN}"]

    def test_batch_custom_requires_addresses(self):
        response = client.post(
            "/api/mailboxes/batch",
            json={"quantity": 2, "password": "batchpassword123", "generation_type": "custom"},
        )
        assert response.status_code == 422

    def test_batch_custom_rejects_other_domain(self):
        response = client.post(
            "/api/mailboxes/batch",
            json={
                "quantity": 1,
                "password": "batchpassword123",
                "generation_type": "custom",
                "custom_addresses": ["intruder@other-domain.com"],
            },
        )
        assert response.status_code == 422

    def test_batch_rejects_duplicate_custom_addresses(self):
        address = f"repeated-batch@{DOMAIN}"
        response = client.post(
            "/api/mailboxes/batch",
            json={
                "quantity": 2,
                "password": "batchpassword123",
                "generation_type": "custom",
                "custom_addresses": [address, address],
            },
        )
        assert response.status_code == 422

    def test_batch_rejects_prefix_with_at_sign(self):
        response = client.post(
            "/api/mailboxes/batch",
            json={
                "quantity": 1,
                "password": "batchpassword123",
                "generation_type": "random",
                "prefix": "evil@other-domain.com",
            },
        )
        assert response.status_code == 422

    def test_create_single_mailbox_other_domain(self):
        response = client.post(
            "/api/mailboxes",
            json={"email_address": "someone@other-domain.com", "password": "securepassword123"},
        )
        assert response.status_code == 422

    def test_create_single_mailbox_normalizes_case(self):
        response = client.post(
            "/api/mailboxes",
            json={"email_address": f"Mixed.Case@{DOMAIN.upper()}", "password": "securepassword123"},
        )
        assert response.status_code == 201
        assert response.json()["email_address"] == f"mixed.case@{DOMAIN}"


class TestAccountPersistence:
    """Accounts persist; only the content they hold expires."""

    def test_new_mailbox_has_no_expiry(self):
        response = client.post(
            "/api/mailboxes",
            json={"email_address": "no-expiry@kupay.site", "password": "securepassword123"},
        )
        assert response.status_code == 201
        assert response.json()["expires_at"] is None

    def test_mailbox_older_than_retention_still_logs_in_and_reads_mail(self):
        address = f"long-lived@{DOMAIN}"
        password = "longlivedpass123"
        created = client.post("/api/mailboxes", json={"email_address": address, "password": password})
        assert created.status_code == 201

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with TestingSessionLocal() as db:
            mailbox = db.query(Mailbox).filter(Mailbox.email_address == address).one()
            mailbox.created_at = now - timedelta(days=120)
            mailbox.expires_at = now - timedelta(days=90)
            db.add(
                Message(
                    mailbox_id=mailbox.id,
                    provider_message_id=f"<{uuid.uuid4()}@worker>",
                    sender="remetente@example.org",
                    recipient=address,
                    subject="Depois de 120 dias",
                    received_at=now,
                    expires_at=now + timedelta(days=30),
                    is_read=False,
                )
            )
            db.commit()

        login = client.post("/api/mailboxes/login", json={"email": address, "password": password})
        assert login.status_code == 200
        token = login.json()["access_token"]

        assert client.get("/api/mailboxes/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200
        listing = client.get("/api/messages", headers={"Authorization": f"Bearer {token}"})
        assert listing.status_code == 200
        assert [item["subject"] for item in listing.json()] == ["Depois de 120 dias"]


class TestDeletedAddresses:
    """Deleted addresses stay registered: recreating one is a conflict, never a 500."""

    def test_deleted_address_cannot_be_recreated(self):
        address = f"deleted-{uuid.uuid4().hex[:8]}@{DOMAIN}"
        password = "deleted-pass-123"
        assert client.post(
            "/api/mailboxes", json={"email_address": address, "password": password}
        ).status_code == 201

        login = client.post("/api/mailboxes/login", json={"email": address, "password": password})
        token = login.json()["access_token"]
        assert client.delete(
            "/api/mailboxes/me", headers={"Authorization": f"Bearer {token}"}
        ).status_code == 204

        again = client.post("/api/mailboxes", json={"email_address": address, "password": password})
        assert again.status_code == 409
        assert "already exists" in again.json()["detail"]

    def test_deleted_address_is_reported_as_taken_in_a_batch(self):
        address = f"deleted-batch-{uuid.uuid4().hex[:8]}@{DOMAIN}"
        password = "deleted-pass-123"
        client.post("/api/mailboxes", json={"email_address": address, "password": password})
        token = client.post(
            "/api/mailboxes/login", json={"email": address, "password": password}
        ).json()["access_token"]
        client.delete("/api/mailboxes/me", headers={"Authorization": f"Bearer {token}"})

        response = client.post(
            "/api/mailboxes/batch",
            json={
                "quantity": 1,
                "password": password,
                "generation_type": "custom",
                "custom_addresses": [address],
            },
        )
        assert response.status_code == 409


class TestBatchSizeLimits:
    def test_custom_batch_cannot_exceed_the_limit(self):
        addresses = [f"massa-{i}@{DOMAIN}" for i in range(101)]
        response = client.post(
            "/api/mailboxes/batch",
            json={
                "quantity": 100,
                "password": "batchpassword123",
                "generation_type": "custom",
                "custom_addresses": addresses,
            },
        )
        assert response.status_code == 422

    def test_batch_quantity_limit_still_applies(self):
        response = client.post(
            "/api/mailboxes/batch",
            json={"quantity": 101, "password": "batchpassword123", "generation_type": "random"},
        )
        assert response.status_code == 422
