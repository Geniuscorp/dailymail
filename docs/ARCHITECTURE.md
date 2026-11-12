# DailyMail Architecture

## Overview

DailyMail is a temporary email service with a layered architecture:

- **Presentation Layer**: React + TypeScript frontend
- **API Layer**: FastAPI REST API
- **Business Logic Layer**: Services and business rules
- **Data Access Layer**: SQLAlchemy ORM
- **Storage Layer**: Cloudflare R2 for attachments
- **External Integration Layer**: Email provider abstraction

## Key Design Principles

1. **Separation of Concerns**: Each layer has clear responsibilities
2. **Provider Abstraction**: Email and storage providers are abstracted
3. **Security First**: Passwords hashed, webhooks validated, access controlled
4. **Sessions via tokens, revocable on purpose**: mailbox sessions are opaque
   and DB-backed (not a stateless JWT) specifically so logout, a password
   change or account deletion take effect immediately, not just on expiry
5. **Simple but Scalable**: SQLite for MVP, easy migration to PostgreSQL later

## Database Schema

### Core Tables

#### mailboxes
- Represents a temporary email address
- Linked to a batch (optional)
- Password protected with Argon2id
- Status: active, blocked, deleted

#### mailbox_sessions
- One row per active login: `mailbox_id`, a SHA-256 hash of the opaque session
  token (the raw token is returned once, at login, and never stored), and an
  expiry (`MAILBOX_SESSION_EXPIRE_DAYS`, 90 days by default)
- Looked up directly by hash on every authenticated request — not decoded
  like a JWT — which is what lets a session be revoked (logout, password
  change, account deletion) instead of only expiring on its own schedule
- A fast hash (not Argon2) is appropriate here: the token already has 256
  bits of entropy from a CSPRNG, so there is nothing to brute-force offline,
  unlike a human-chosen password

#### batches
- Represents a group of emails created together
- Stores shared password hash
- Tracks generation type (random, custom)

#### messages
- Email messages received
- References mailbox and original provider ID
- Stores parsed content and sanitized HTML
- Linked to attachments
- Expires after 30 days

#### attachments
- File metadata (not the files themselves)
- References storage key in R2
- Original filename for display
- MIME type and size for validation

#### admin_users
- Admin account credentials
- Status tracking

#### admin_audit_logs
- Tracks admin actions for security

## API Structure

```
/api/
  /mailboxes           # User email operations
  /messages            # User message access
    /stream            # SSE push: a nudge when new mail lands (see below)
  /attachments         # User attachment access
  /webhooks            # External provider webhooks
  /admin/              # Admin operations
    /dashboard
    /mailboxes
    /batches
    /messages
    /attachments
```

## Real-time Inbox Updates

`GET /api/messages/stream` is a Server-Sent Events connection: the frontend
opens it once per inbox visit and gets pushed a nudge as soon as
`MessageService.ingest()` stores a new message for that mailbox, instead of
polling `GET /messages` on a timer. The fan-out is an in-process
`MailboxEventBroker` (`app/core/events.py`) — fine for the single uvicorn
worker this API runs as, but it would need moving to Redis pub/sub (or
similar) before running more than one process, since a push would otherwise
only reach whichever process happens to hold the subscriber.

The route deliberately does not use the request-scoped `get_db` dependency:
SQLite only has one connection in the whole app (`StaticPool`), and this
response can stay open for as long as a browser tab is, so holding that
session for the connection's lifetime would freeze every other request. It
resolves the mailbox with its own short-lived session instead, closed before
the (potentially hours-long) event loop starts. A 30s poll stays as a backup
on the frontend in case a stream silently gets stuck (e.g. a buffering proxy
between the browser and nginx that neither `X-Accel-Buffering: no` nor
nginx's own `proxy_buffering off` reach).

## Authentication

### Mailbox Access
- Email + password based, checked once: at `POST /mailboxes` (creation) and
  `POST /mailboxes/login`
- Login returns an opaque, long-lived session token (see `mailbox_sessions`
  above), not a JWT — the frontend keeps it in `localStorage`, so the inbox
  stays open across browser restarts instead of asking for the password
  again on every visit
- `POST /mailboxes/logout` revokes only that one session; changing the
  password revokes every *other* session for the mailbox; deleting the
  mailbox revokes all of them

### Admin Access
- Username + password with Argon2id hashing
- Separate admin-scoped JWT (short-lived, `ADMIN_TOKEN_EXPIRE_MINUTES`) —
  deliberately a different mechanism from mailbox sessions, since an
  operator session is not meant to outlive the browser tab the way a
  mailbox's is
- Mailbox tokens and admin tokens are mutually rejected by each other's API
- All admin actions logged to `admin_audit_logs`

## Storage

### Attachment Storage
- Files stored in Cloudflare R2 (S3-compatible API via boto3)
- Database stores only metadata and reference key; storage keys are random
  (`uuid4().hex`), never derived from the original filename
- Downloads are streamed by the backend through an authenticated route; R2
  itself is never exposed publicly
- Attachment storage is best-effort, not all-or-nothing: an attachment is
  validated by file signature (not the sender's claimed MIME type) and
  dropped — logged, not raised — if it fails policy, if R2 is not
  configured, or if the upload itself fails. The message's subject and body
  are always kept regardless; only the one problem attachment is missing.
  This matters because the alternative (failing the whole delivery) is
  surfaced to the sender as an SMTP bounce, which is worse than a message
  arriving without one attachment

## External Integrations

### Inbound Email Provider

`app/providers/` abstracts the inbound source behind one interface
(`InboundEmailProvider.verify()` + `.parse()`), selected by
`INBOUND_EMAIL_PROVIDER`. Two implementations exist:

#### forwardemail.net (`forward_email`, default)
- forwardemail.net receives mail for the domain and POSTs it, already
  parsed as JSON (via the `mailparser` library), to the webhook
- No HMAC signing available on the free plan; `verify()` instead resolves
  the caller's IP via reverse DNS and checks it against
  `mx1.forwardemail.net` / `mx2.forwardemail.net` — still sound, since that
  lookup runs against the real TCP source IP, not a spoofable header
- Chosen over Cloudflare Email Routing after Cloudflare's own built-in
  anti-spam filtering was found to silently drop mail from a real sender
  (no bounce, nothing in Cloudflare's own activity log) — confirmed by
  bypassing the Worker entirely and still seeing nothing arrive

#### Cloudflare Email Worker (`cloudflare_worker`, kept as an alternative)
- Cloudflare Email Routing receives emails for the domain
- A dedicated Cloudflare Worker (`worker/`) converts the MIME email to a
  JSON payload, signs it with HMAC-SHA256, and POSTs it to the webhook
- `verify()` checks that signature + a timestamp-tolerance window
- Known limitation (see above): Cloudflare's own spam filtering runs
  ahead of the Worker and can drop mail from some senders with no trace

## Security Measures

1. **Password Storage**: Argon2id hashing
2. **Rate Limiting**: Applied to mailbox creation, login and the inbound
   webhook, per client IP, in-process (see Scalability below). Correct IP
   attribution requires the proxy in front of uvicorn to be explicitly
   trusted (`--forwarded-allow-ips`, set in `backend/Dockerfile`) — without
   it, every request looks like it comes from the proxy's own address and
   the limiter becomes one shared budget for every visitor instead of one
   per client
3. **CORS**: Allow-listed origins via `CORS_ALLOWED_ORIGINS`, not hardcoded
4. **Input Validation**: Pydantic schemas for all inputs
5. **SQL Injection**: Protected via SQLAlchemy ORM
6. **XSS Prevention**: HTML sanitized before storage (`nh3`, allow-listed
   tags/schemes) and rendered in a sandboxed iframe with its own CSP on the
   frontend — defence in depth, not just one layer
7. **Path Traversal**: Filenames never used directly in storage paths
8. **Webhook Validation**: HMAC-SHA256 signature and timestamp-tolerance
   check before the payload is parsed
9. **Token Secret**: the app refuses to start in production
   (`ENVIRONMENT=production`) with a missing, empty or placeholder
   `ACCESS_TOKEN_SECRET`, or one under 32 characters
10. **Session Revocation**: mailbox sessions are opaque and DB-backed, so
    logout, a password change or account deletion take effect immediately —
    unlike a stateless JWT, which stays valid until it expires on its own
11. **Audit Logging**: Admin actions recorded in `admin_audit_logs`

## Scalability Considerations

### Current (single process by design)
- SQLite with a single pooled connection (`StaticPool`): one writer for the
  whole app
- Rate limiting counters live in process memory (`app/core/rate_limit.py`)
- The SSE push fan-out (`app/core/events.py`) is also in-process pub/sub
- The retention sweep runs as a background `asyncio` task started in
  `app/main.py`'s lifespan, not a separate cron job/container — this is a
  deliberate simplification, not a limitation: it needs no shared state
  with any other process, and keeps working unchanged if the app is ever
  split across more than one of them (each instance just sweeps on its own
  schedule; the operation is idempotent, so running it from more than one
  process is harmless, just redundant)

These three are the reason the API intentionally runs as **one** uvicorn
worker (see `backend/Dockerfile`). Mailbox sessions, by contrast, are
already DB-backed and would scale across processes fine as-is.

### Path to more than one process
1. **PostgreSQL**: replaces SQLite's single-writer limitation
2. **Redis**: shared rate-limit counters, replacing the in-process limiter
3. **Redis pub/sub** (or similar): replaces the in-process SSE broker, so a
   push reaches a subscriber regardless of which process holds it
4. **Load Balancer**: multiple backend instances
5. **CDN**: static asset caching

## Error Handling

- Consistent error response format
- No sensitive information in error messages
- Webhook failures retried (TBD)
- Transaction rollback on database errors
