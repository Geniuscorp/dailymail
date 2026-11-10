"""Tests for mailbox operations."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import get_db
from app.models import Base

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


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
