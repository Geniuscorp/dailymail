"""Application configuration from environment variables."""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Application
    app_name: str = "DailyMail"
    environment: str = "development"
    debug: bool = True

    # Database
    database_url: str = "sqlite:///./dailymail.db"

    # Domain
    domain: str = "kupay.site"

    # Security
    access_token_secret: str = "your-secret-key-change-in-production"
    access_token_expire_minutes: int = 1440

    # Admin
    admin_username: str = "admin"
    admin_password_hash: str = ""
    admin_api_secret: str = ""

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


@lru_cache()
def get_settings() -> Settings:
    return Settings()
