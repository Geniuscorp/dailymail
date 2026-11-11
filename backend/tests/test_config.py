"""The app must refuse to boot in production with a forgeable token secret."""
import pytest

from app.core.config import Settings


def _settings(**overrides) -> Settings:
    defaults = {
        "environment": "production",
        "access_token_secret": "a" * 32,
        "inbound_email_provider": "cloudflare_worker",
        "inbound_webhook_secret": "test-webhook-secret",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_production_rejects_the_placeholder_secret():
    with pytest.raises(ValueError, match="ACCESS_TOKEN_SECRET"):
        _settings(access_token_secret="your-secret-key-change-in-production")


def test_production_rejects_an_empty_secret():
    with pytest.raises(ValueError, match="ACCESS_TOKEN_SECRET"):
        _settings(access_token_secret="")


def test_production_rejects_a_short_secret():
    with pytest.raises(ValueError, match="ACCESS_TOKEN_SECRET"):
        _settings(access_token_secret="too-short")


def test_production_accepts_a_real_secret():
    _settings(access_token_secret="a" * 32)


def test_development_tolerates_the_placeholder_secret():
    Settings(
        environment="development",
        access_token_secret="your-secret-key-change-in-production",
    )
