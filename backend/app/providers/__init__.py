"""Abstraction layer for external providers."""
from app.core.config import get_settings
from app.providers.base import InboundEmailProvider
from app.providers.cloudflare_worker import CloudflareWorkerProvider
from app.providers.forward_email import ForwardEmailProvider

__all__ = ["InboundEmailProvider", "build_inbound_provider"]


def build_inbound_provider() -> InboundEmailProvider:
    settings = get_settings()
    if settings.inbound_email_provider == "cloudflare_worker":
        return CloudflareWorkerProvider(
            secret=settings.inbound_webhook_secret,
            tolerance_seconds=settings.inbound_webhook_tolerance_seconds,
        )
    if settings.inbound_email_provider == "forward_email":
        return ForwardEmailProvider()
    raise RuntimeError(f"Unsupported INBOUND_EMAIL_PROVIDER: {settings.inbound_email_provider!r}")
