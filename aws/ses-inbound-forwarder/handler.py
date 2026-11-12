"""AWS Lambda: turns a raw inbound email stored in S3 by an SES receipt rule
into the same signed JSON webhook DailyMail's backend already accepts from
the Cloudflare Worker (see backend/app/providers/cloudflare_worker.py).

Why this exists: SES itself has no concept of "send me a JSON webhook", only
S3/SNS/Lambda receipt actions. This function is the small translation layer
between "raw MIME in S3" and "the HTTP POST our backend understands" - it
intentionally does NOT introduce a new payload format or new verification
scheme, so the backend needs zero new parsing code for this provider.

Deploy: paste this file as-is into a Python 3.12 Lambda (console inline
editor is fine, no dependencies beyond the stdlib + the boto3 that AWS
already bundles in every Python Lambda runtime). See docs/DEPLOYMENT.md for
the full step-by-step (S3 bucket, SES receipt rule, Lambda env vars, IAM).

Required Lambda environment variables:
  WEBHOOK_URL    e.g. https://mail.kupay.site/api/webhooks/inbound-email
  WEBHOOK_SECRET must equal INBOUND_WEBHOOK_SECRET on the backend
  BUCKET_NAME    the S3 bucket the SES rule's "S3" action stores raw mail in
  BUCKET_PREFIX  optional, must match the "S3" action's object key prefix
"""
import base64
import email
import email.utils
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
from email.policy import default as default_policy

import boto3

s3 = boto3.client("s3")

# Only the first recipient is ingested when one email is addressed to more
# than one of our mailboxes at once - same documented simplification as the
# forward_email provider (app/providers/forward_email.py).


def _sender_address(mail: dict, msg) -> str:
    source = mail.get("source") or msg.get("From", "")
    _, address = email.utils.parseaddr(source)
    return (address or "").lower()


def _body_and_attachments(msg):
    text_body = None
    html_body = None
    attachments = []

    if not msg.is_multipart():
        payload = msg.get_payload(decode=True)
        if payload is None:
            return text_body, html_body, attachments
        decoded = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
        if msg.get_content_type() == "text/html":
            html_body = decoded
        else:
            text_body = decoded
        return text_body, html_body, attachments

    for part in msg.walk():
        if part.is_multipart():
            continue
        content_type = part.get_content_type()
        disposition = part.get_content_disposition()
        is_body_candidate = disposition != "attachment" and content_type in ("text/plain", "text/html")

        if is_body_candidate and content_type == "text/plain" and text_body is None:
            payload = part.get_payload(decode=True)
            if payload is not None:
                text_body = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
            continue
        if is_body_candidate and content_type == "text/html" and html_body is None:
            payload = part.get_payload(decode=True)
            if payload is not None:
                html_body = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
            continue

        # Anything else with content is treated as an attachment: inline
        # images, real attachments, and any part we don't otherwise recognize.
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        attachments.append(
            {
                "filename": part.get_filename(),
                "content_type": content_type,
                "content_base64": base64.b64encode(payload).decode("ascii"),
            }
        )

    return text_body, html_body, attachments


def _forward(payload: dict, webhook_url: str, secret: str) -> None:
    body = json.dumps(payload).encode("utf-8")
    timestamp = str(int(time.time()))
    signature = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()

    request = urllib.request.Request(
        webhook_url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-DailyMail-Timestamp": timestamp,
            "X-DailyMail-Signature": signature,
        },
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        response.read()


def handler(event, context):
    # A scheduled EventBridge rule pings this function every few minutes with
    # a plain {"source": "aws.events", ...} event (no "Records") just to keep
    # it warm and avoid a cold-start delay on the next real delivery.
    if "Records" not in event:
        return {"statusCode": 200, "body": "warmup ping"}

    webhook_url = os.environ["WEBHOOK_URL"]
    webhook_secret = os.environ["WEBHOOK_SECRET"]
    bucket_name = os.environ["BUCKET_NAME"]
    bucket_prefix = os.environ.get("BUCKET_PREFIX", "")

    for record in event["Records"]:
        mail = record["ses"]["mail"]
        receipt = record["ses"]["receipt"]
        message_id = mail["messageId"]

        recipients = receipt.get("recipients") or []
        if not recipients:
            continue
        recipient = recipients[0].lower()

        obj = s3.get_object(Bucket=bucket_name, Key=f"{bucket_prefix}{message_id}")
        raw_bytes = obj["Body"].read()
        msg = email.message_from_bytes(raw_bytes, policy=default_policy)

        text_body, html_body, attachments = _body_and_attachments(msg)

        payload = {
            "message_id": message_id,
            "sender": _sender_address(mail, msg),
            "recipient": recipient,
            "subject": msg.get("subject"),
            "text": text_body,
            "html": html_body,
            "received_at": mail.get("timestamp"),
            "attachments": attachments,
        }

        try:
            _forward(payload, webhook_url, webhook_secret)
        except urllib.error.HTTPError as exc:
            # Let Lambda retry/report this invocation as failed rather than
            # silently losing the message - SES already stored the raw copy
            # in S3, so nothing is lost even if this attempt fails.
            raise RuntimeError(f"Webhook rejected delivery: {exc.code} {exc.read()[:500]!r}") from exc

        # The backend has the message now; remove the extra, unencrypted
        # copy SES stored in S3 instead of keeping it indefinitely.
        s3.delete_object(Bucket=bucket_name, Key=f"{bucket_prefix}{message_id}")
