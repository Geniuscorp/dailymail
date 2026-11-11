"""Tests for abuse protection on the open endpoints: rate limits and creation secret."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.main import app

client = TestClient(app)
DOMAIN = get_settings().domain


@pytest.fixture(autouse=True)
def _reset_limiter():
    limiter.reset()
    yield
    limiter.reset()


def _address(prefix: str = "proto") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@{DOMAIN}"


def _create(address: str, password: str = "protected-pass-123", **kwargs):
    return client.post("/api/mailboxes", json={"email_address": address, "password": password}, **kwargs)


def _create_batch(**kwargs):
    return client.post(
        "/api/mailboxes/batch",
        json={"quantity": 1, "password": "protected-pass-123", "generation_type": "random"},
        **kwargs,
    )


def _enable_limits(monkeypatch, create_limit=None, login_limit=None):
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    if create_limit is not None:
        monkeypatch.setattr(settings, "rate_limit_create_per_minute", create_limit)
    if login_limit is not None:
        monkeypatch.setattr(settings, "rate_limit_login_per_minute", login_limit)


class TestRateLimiting:
    def test_creation_limit_returns_429_with_retry_after(self, monkeypatch):
        _enable_limits(monkeypatch, create_limit=2)

        assert _create(_address()).status_code == 201
        assert _create(_address()).status_code == 201

        blocked = _create(_address())
        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) >= 1

    def test_single_and_batch_share_the_same_budget(self, monkeypatch):
        _enable_limits(monkeypatch, create_limit=1)

        assert _create(_address()).status_code == 201
        assert _create_batch().status_code == 429

    def test_login_attempts_are_limited(self, monkeypatch):
        address = _address("login-limit")
        assert _create(address).status_code == 201
        _enable_limits(monkeypatch, login_limit=2)

        for _ in range(2):
            attempt = client.post("/api/mailboxes/login", json={"email": address, "password": "wrong-pass"})
            assert attempt.status_code == 401

        blocked = client.post("/api/mailboxes/login", json={"email": address, "password": "wrong-pass"})
        assert blocked.status_code == 429

    def test_limiter_can_be_disabled(self, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "rate_limit_enabled", False)
        monkeypatch.setattr(settings, "rate_limit_create_per_minute", 1)

        for _ in range(3):
            assert _create(_address()).status_code == 201


class TestWebhookRateLimiting:
    def test_inbound_webhook_is_rate_limited(self, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "rate_limit_enabled", True)
        monkeypatch.setattr(settings, "rate_limit_webhook_per_minute", 1)

        # No valid signature is needed: the limit is enforced before the
        # payload is even read, so an unauthenticated caller cannot use it to
        # force free repeated work.
        first = client.post("/api/webhooks/inbound-email", content=b"{}")
        assert first.status_code in (401, 503)

        blocked = client.post("/api/webhooks/inbound-email", content=b"{}")
        assert blocked.status_code == 429


class TestCreationSecret:
    def test_creation_requires_the_secret_when_configured(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "mailbox_creation_secret", "s3cret-value")

        assert _create(_address()).status_code == 403
        assert _create(_address(), headers={"X-DailyMail-Creation-Secret": "wrong"}).status_code == 403
        allowed = _create(_address(), headers={"X-DailyMail-Creation-Secret": "s3cret-value"})
        assert allowed.status_code == 201

    def test_batch_creation_requires_the_secret_too(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "mailbox_creation_secret", "s3cret-value")

        assert _create_batch().status_code == 403
        assert _create_batch(headers={"X-DailyMail-Creation-Secret": "s3cret-value"}).status_code == 201

    def test_login_does_not_need_the_creation_secret(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "mailbox_creation_secret", "s3cret-value")
        address = _address("login-secret")
        _create(address, headers={"X-DailyMail-Creation-Secret": "s3cret-value"})

        login = client.post("/api/mailboxes/login", json={"email": address, "password": "protected-pass-123"})
        assert login.status_code == 200

    def test_creation_is_open_when_no_secret_is_configured(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "mailbox_creation_secret", "")

        assert _create(_address()).status_code == 201
