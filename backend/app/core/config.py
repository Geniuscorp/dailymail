"""Application configuration from environment variables."""
from pydantic import model_validator
from pydantic_settings import BaseSettings
from functools import lru_cache

# Anyone who knows this value can forge a token for any mailbox or the admin
# account. It must never be reachable in production.
_INSECURE_DEFAULT_SECRET = "your-secret-key-change-in-production"


class Settings(BaseSettings):
    # Application
    app_name: str = "DailyMail"
    environment: str = "development"
    debug: bool = True

    # Database
    database_url: str = "sqlite:///./dailymail.db"

    # Domain
    domain: str = "kupay.site"
    # Comma-separated list of origins the frontend is actually served from.
    # Keep this in sync with wherever `web` is really reachable: a frontend
    # origin that is not listed here gets its requests rejected by CORS.
    cors_allowed_origins: str = "https://temp.kupay.site,http://localhost:3000,http://localhost:5173"

    # Security
    # No safe default on purpose: an empty or placeholder value is rejected at
    # startup in production (see validate_production_secrets below) instead of
    # silently signing admin tokens with a value anyone can read in this file.
    access_token_secret: str = _INSECURE_DEFAULT_SECRET
    # How long a mailbox stays signed in without acting, like mail.tm: the
    # session token is opaque and stored (hashed) in the database, not a JWT,
    # so it can be revoked (logout, password change) instead of just expiring.
    mailbox_session_expire_days: int = 90

    # Abuse protection (per client IP, per process).
    rate_limit_enabled: bool = True
    rate_limit_create_per_minute: int = 10
    rate_limit_login_per_minute: int = 10
    rate_limit_webhook_per_minute: int = 120
    # When set, creating mailboxes requires the X-DailyMail-Creation-Secret header.
    mailbox_creation_secret: str = ""

    # Admin
    admin_username: str = "admin"
    admin_password_hash: str = ""
    admin_token_expire_minutes: int = 480

    # Cloudflare R2
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = "dailymail-attachments"
    # Optional override for the S3-compatible endpoint (local testing only).
    r2_endpoint_url: str = ""

    # Inbound Email
    inbound_email_provider: str = "cloudflare_worker"
    inbound_webhook_secret: str = ""
    inbound_webhook_tolerance_seconds: int = 300
    # Base64 attachments inflate the JSON payload by about a third.
    max_inbound_payload_mb: int = 40

    # Attachment limits
    max_attachment_size_mb: int = 20
    max_attachments_per_message: int = 10

    # Email retention
    email_retention_days: int = 30

    class Config:
        env_file = ".env"
        case_sensitive = False

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        """Refuse to boot in production with a forgeable or missing secret."""
        if self.environment == "production":
            if not self.access_token_secret or self.access_token_secret == _INSECURE_DEFAULT_SECRET:
                raise ValueError(
                    "ACCESS_TOKEN_SECRET must be set to a unique random value in production "
                    "(generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\")"
                )
            if len(self.access_token_secret) < 32:
                raise ValueError("ACCESS_TOKEN_SECRET must be at least 32 characters in production")
        return self


@lru_cache()
def get_settings() -> Settings:
    return Settings()
