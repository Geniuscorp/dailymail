"""Tests for the forwardemail.net inbound provider."""
import json
import socket

import pytest

from app.providers.base import InvalidWebhookError
from app.providers.forward_email import ForwardEmailProvider

provider = ForwardEmailProvider()


def _payload(**overrides) -> bytes:
    data = {
        "subject": "Olá",
        "text": "Corpo em texto",
        "html": "<p>Corpo em texto</p>",
        "messageId": "<abc123@example.net>",
        "from": {"value": [{"address": "remetente@example.net", "name": "Someone"}]},
        "recipients": ["caixa@kupay.site"],
        "session": {
            "recipient": "caixa@kupay.site",
            "sender": "remetente@example.net",
            "arrivalDate": "2026-01-10T12:00:00.000Z",
        },
        "attachments": [],
    }
    data.update(overrides)
    return json.dumps(data).encode()


class TestParse:
    def test_parses_a_typical_message(self):
        message = provider.parse(_payload())
        assert message.provider_message_id == "<abc123@example.net>"
        assert message.sender == "remetente@example.net"
        assert message.recipient == "caixa@kupay.site"
        assert message.subject == "Olá"
        assert message.text_body == "Corpo em texto"
        assert message.html_body == "<p>Corpo em texto</p>"
        assert message.received_at is not None
        assert message.received_at.year == 2026

    def test_mailparser_false_body_means_no_body(self):
        # mailparser represents a genuinely absent text/html part as the
        # boolean `false`, not `null` or an empty string.
        message = provider.parse(_payload(text=False, html=False))
        assert message.text_body is None
        assert message.html_body is None

    def test_missing_message_id_gets_a_fallback(self):
        message = provider.parse(_payload(messageId=None))
        assert message.provider_message_id.startswith("<")
        assert "@forwardemail.local" in message.provider_message_id

    def test_sender_falls_back_to_the_from_header_when_session_sender_is_blank(self):
        payload = _payload()
        data = json.loads(payload)
        data["session"]["sender"] = ""
        message = provider.parse(json.dumps(data).encode())
        assert message.sender == "remetente@example.net"

    def test_missing_recipient_is_rejected(self):
        payload = _payload()
        data = json.loads(payload)
        data["session"]["recipient"] = ""
        with pytest.raises(InvalidWebhookError):
            provider.parse(json.dumps(data).encode())

    def test_missing_sender_is_rejected(self):
        payload = _payload()
        data = json.loads(payload)
        data["session"]["sender"] = ""
        data["from"] = None
        with pytest.raises(InvalidWebhookError):
            provider.parse(json.dumps(data).encode())

    def test_addresses_are_lowercased(self):
        payload = _payload()
        data = json.loads(payload)
        data["session"]["recipient"] = "Caixa@KUPAY.site"
        data["session"]["sender"] = "Remetente@Example.NET"
        message = provider.parse(json.dumps(data).encode())
        assert message.recipient == "caixa@kupay.site"
        assert message.sender == "remetente@example.net"

    def test_malformed_json_is_rejected(self):
        with pytest.raises(InvalidWebhookError):
            provider.parse(b"not json")

    def test_non_object_json_is_rejected(self):
        with pytest.raises(InvalidWebhookError):
            provider.parse(b"[1, 2, 3]")

    def test_grouped_recipients_do_not_crash_the_parse(self, caplog):
        # One email addressed to two of our mailboxes at once: only the
        # delivery's own session.recipient is ingested, but it must not
        # raise or silently lose track of the fact that it happened.
        message = provider.parse(_payload(recipients=["a@kupay.site", "b@kupay.site"]))
        assert message.recipient == "caixa@kupay.site"
        assert any("grouped" in rec.message for rec in caplog.records)

    def test_attachment_buffer_is_decoded_to_bytes(self):
        payload = _payload(
            attachments=[
                {
                    "filename": "ola.txt",
                    "contentType": "text/plain",
                    "content": {"type": "Buffer", "data": list(b"hello world!")},
                }
            ]
        )
        message = provider.parse(payload)
        assert len(message.attachments) == 1
        attachment = message.attachments[0]
        assert attachment.filename == "ola.txt"
        assert attachment.declared_content_type == "text/plain"
        assert attachment.data == b"hello world!"

    def test_attachment_without_buffered_content_is_dropped_not_fatal(self):
        payload = _payload(attachments=[{"filename": "x.txt", "contentType": "text/plain"}])
        message = provider.parse(payload)
        assert message.attachments == ()


class TestVerify:
    @pytest.mark.asyncio
    async def test_accepts_a_trusted_sending_host(self, monkeypatch):
        monkeypatch.setattr(
            socket, "gethostbyaddr", lambda ip: ("mx1.forwardemail.net", [], [ip])
        )
        await provider.verify({}, b"{}", client_ip="203.0.113.1")

    @pytest.mark.asyncio
    async def test_rejects_an_untrusted_sending_host(self, monkeypatch):
        monkeypatch.setattr(
            socket, "gethostbyaddr", lambda ip: ("evil.example.com", [], [ip])
        )
        with pytest.raises(InvalidWebhookError):
            await provider.verify({}, b"{}", client_ip="203.0.113.1")

    @pytest.mark.asyncio
    async def test_rejects_when_reverse_dns_fails(self, monkeypatch):
        def _raise(ip):
            raise socket.herror("unknown host")

        monkeypatch.setattr(socket, "gethostbyaddr", _raise)
        with pytest.raises(InvalidWebhookError):
            await provider.verify({}, b"{}", client_ip="203.0.113.1")

    @pytest.mark.asyncio
    async def test_rejects_when_there_is_no_client_ip(self):
        with pytest.raises(InvalidWebhookError):
            await provider.verify({}, b"{}", client_ip=None)
