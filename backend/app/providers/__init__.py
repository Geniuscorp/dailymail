"""Abstraction layer for external providers."""
from app.core.config import get_settings
from app.providers.base import InboundEmailProvider
from app.providers.cloudflare_worker import CloudflareWorkerProvider
from app.providers.forward_email import ForwardEmailProvider

__all__ = ["InboundEmailProvider", "build_inbound_provider"]


def build_inbound_provider() -> InboundEmailProvider:
    settings = get_settings()
    if settings.inbound_email_provider in ("cloudflare_worker", "aws_ses"):
        # Both values point at the exact same signed-JSON-webhook contract
        # (see CloudflareWorkerProvider's docstring): the Cloudflare Worker
        # and the AWS Lambda forwarder (aws/ses-inbound-forwarder/) each
        # build the same payload shape and sign it the same way, so there is
        # nothing provider-specific left for this class to do differently.
        return CloudflareWorkerProvider(
            secret=settings.inbound_webhook_secret,
            tolerance_seconds=settings.inbound_webhook_tolerance_seconds,
        )
    if settings.inbound_email_provider == "forward_email":
        return ForwardEmailProvider()
    raise RuntimeError(f"Unsupported INBOUND_EMAIL_PROVIDER: {settings.inbound_email_provider!r}")
