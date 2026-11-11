# DailyMail API Documentation

## Overview

Base URL: `http://localhost:8000/api` (development)
Base URL: `https://mail.kupay.site/api` (production; same origin as the frontend, proxied by nginx)

All requests and responses use JSON.

## Health Check

```
GET /health
```

Returns service status.

Response:
```json
{
  "status": "healthy",
  "environment": "development"
}
```

## Authentication

### Mailbox Authentication

POST `/mailboxes/login` with email and password returns:
```json
{
  "access_token": "...",
  "token_type": "bearer",
  "expires_in": 7776000
}
```

Include token in Authorization header:
```
Authorization: Bearer <token>
```

The password is only needed again if the session is revoked (logout, password
change on another device) or outlives `MAILBOX_SESSION_EXPIRE_DAYS` (90 days by
default) without being used — the token itself is opaque and stored (hashed)
server-side, not a JWT, so it survives browser restarts and can be revoked.

### Admin Authentication

POST `/admin/login` with username and password returns similar token.

## Endpoints

### Mailboxes

#### Create Mailbox
```
POST /mailboxes
```

Request:
```json
{
  "email_address": "user@kupay.site",
  "password": "secure_password"
}
```

If `MAILBOX_CREATION_SECRET` is configured, this request also needs the
`X-DailyMail-Creation-Secret` header (see Mailbox Creation Secret).

The address must belong to the configured `DOMAIN`; other domains are rejected with `422`.
The address is stored lowercased, and a reserved local part (`admin`, `postmaster`, ...) or an
existing address returns `409`.

#### Create Batch
```
POST /mailboxes/batch
```

Request:
```json
{
  "quantity": 10,
  "generation_type": "random",
  "password": "common_password",
  "prefix": "test"
}
```

Generated and custom addresses are always qualified with the configured `DOMAIN`, so this
returns entries such as `test001@kupay.site`. With `generation_type: "custom"`,
`custom_addresses` is required and every entry must be on that domain; duplicates return `422`.
A batch is capped at 100 addresses, including `custom_addresses`.

#### Login
```
POST /mailboxes/login
```

Request:
```json
{
  "email": "user@example.com",
  "password": "password"
}
```

#### Logout
```
POST /mailboxes/logout
```

Requires authentication. Revokes only the current session; other devices stay signed in.

#### Get Mailbox Info
```
GET /mailboxes/me
```

Requires authentication.

#### Update Password
```
PATCH /mailboxes/me/password
```

Request:
```json
{
  "current_password": "old",
  "new_password": "new"
}
```

Revokes every other session for this mailbox; the device making the request stays signed in.

#### Delete Mailbox
```
DELETE /mailboxes/me
```

Requires authentication.

### Messages

#### List Messages
```
GET /messages
```

Query parameters:
- `limit`: number of messages (default: 20)
- `offset`: pagination offset (default: 0)

#### Get Message
```
GET /messages/{message_id}
```

#### Mark as Read
```
PATCH /messages/{message_id}/read
```

Request:
```json
{
  "is_read": true
}
```

#### Delete Message
```
DELETE /messages/{message_id}
```

### Attachments

#### Get Attachment Info
```
GET /attachments/{attachment_id}
```

#### Download Attachment
```
GET /attachments/{attachment_id}/download
GET /attachments/{attachment_id}/download?inline=true
```

Requires the owning mailbox's bearer token; other mailboxes receive 404. Bytes are streamed by the backend from R2; R2 is never exposed publicly. Responses carry `X-Content-Type-Options: nosniff` and `Cache-Control: private, no-store`. Downloads use `Content-Disposition: attachment`. `inline=true` is honoured only for PDF and images and adds `Content-Security-Policy: sandbox; default-src 'none'`.

Deleting a message deletes its objects from R2.

### Webhooks

#### Inbound Email
```
POST /webhooks/inbound-email
```

Called by the Cloudflare Email Worker (see `worker/README.md`).

Headers:
- `X-DailyMail-Timestamp`: unix seconds; rejected if outside `INBOUND_WEBHOOK_TOLERANCE_SECONDS`
- `X-DailyMail-Signature`: hex HMAC-SHA256 of `"<timestamp>.<raw body>"` using `INBOUND_WEBHOOK_SECRET`

Body:
```json
{
  "message_id": "<unique@sender>",
  "sender": "alice@example.com",
  "recipient": "box@kupay.site",
  "subject": "Olá",
  "text": "plain body",
  "html": "<p>html body</p>",
  "received_at": "2026-01-10T12:00:00Z"
}
```

Responses: `202 {"status": "stored"|"duplicate"|"ignored"}` (`ignored` for unknown or inactive recipients), `401` for authentication failures, `413` above `MAX_INBOUND_PAYLOAD_MB`, `503` when the secret is not configured.

Attachments are accepted as `attachments: [{filename, content_type, content_base64}]`. Each one is kept only if its extension is allowed (pdf, png, jpg, jpeg, gif, txt, doc, docx, xls, xlsx, zip), its content matches that format's signature, and it is within `MAX_ATTACHMENT_SIZE_MB`. Up to `MAX_ATTACHMENTS_PER_MESSAGE` are kept. Rejected attachments are dropped and the message is still stored. The stored MIME type comes from the allow-list, never from the sender.

### Admin Endpoints

Admin endpoints require an admin-scoped token: `POST /admin/login` returns it, and it
goest in `Authorization: Bearer <token>`. Mailbox tokens are rejected by the admin
API and admin tokens are rejected by the mailbox API. The first login bootstraps the
admin account from `ADMIN_USERNAME` / `ADMIN_PASSWORD_HASH` when no admin exists yet.

#### Admin Login
```
POST /admin/login
```

Request: `{"username": "admin", "password": "..."}`. Returns the same token shape as
mailbox login, `401` for bad credentials, `503` when no admin is configured.

#### Dashboard
```
GET /admin/dashboard
```

Returns statistics:
```json
{
  "total_mailboxes": 100,
  "active_mailboxes": 95,
  "total_messages": 1500,
  "total_attachments": 300,
  "storage_used_mb": 2500,
  "expiring_soon": 5
}
```

#### List Mailboxes
```
GET /admin/mailboxes
```

Query parameters:
- `search`: search by email
- `status`: filter by status (`active`, `blocked`, `deleted`)
- `limit`: number per page (default 50, max 200)
- `offset`: pagination

Returns `{total, limit, offset, items}`; each item carries `message_count`.

#### List Batches
```
GET /admin/batches
```

Returns `{total, limit, offset, items}` with `mailbox_count` per batch.

#### Manage Mailboxes
```
PATCH /admin/mailboxes/{mailbox_id}
PATCH /admin/batches/{batch_id}/password
DELETE /admin/mailboxes/{mailbox_id}
```

`PATCH /admin/mailboxes/{id}` accepts `{"status": "active"|"blocked"|"deleted"}`.
`DELETE` is a soft delete: the account stops logging in, its messages age out through
the retention window. `PATCH /admin/batches/{id}/password` takes
`{"new_password": "..."}` and updates every mailbox in the batch.

#### Manage Messages
```
GET /admin/messages
DELETE /admin/messages/{message_id}
```

Filters: `search` (sender, recipient or subject), `mailbox_id`, `limit`, `offset`.
Admin views include messages already past their retention window until the sweep runs.
`DELETE` removes the stored attachments from R2 as well; it returns `503` if storage
is not configured and the message has attachments.

#### Manage Attachments
```
GET /admin/attachments
DELETE /admin/attachments/{attachment_id}
```

Filters: `message_id`, `limit`, `offset`.

Every mutating admin action is written to `admin_audit_logs` (`mailbox.status`,
`mailbox.delete`, `batch.password`, `message.delete`, `attachment.delete`).
```

## Error Responses

Standard error format:
```json
{
  "detail": "Error message describing what went wrong"
}
```

HTTP Status Codes:
- `200`: Success
- `201`: Created
- `400`: Bad Request
- `401`: Unauthorized
- `403`: Forbidden
- `404`: Not Found
- `409`: Conflict (e.g., email already exists)
- `413`: Payload Too Large
- `422`: Validation Error
- `429`: Too Many Requests (see Rate Limiting)
- `500`: Server Error

## Rate Limiting

Applied per client IP and per backend process, in a sliding one-minute window:

- `POST /mailboxes` and `POST /mailboxes/batch` share one budget
  (`RATE_LIMIT_CREATE_PER_MINUTE`, default 10)
- `POST /mailboxes/login` (`RATE_LIMIT_LOGIN_PER_MINUTE`, default 10)

Exceeding a limit returns `429` with a `Retry-After` header (seconds). Set
`RATE_LIMIT_ENABLED=false` only for local development. Because the counters are
in-process, each uvicorn worker keeps its own budget.

## Mailbox Creation Secret

When `MAILBOX_CREATION_SECRET` is set, both creation endpoints require the shared
secret in a header; requests without it (or with a wrong value) return `403`.

```
X-DailyMail-Creation-Secret: <MAILBOX_CREATION_SECRET>
```

Login, message and attachment endpoints do not use this header. Leaving the
setting empty keeps creation open, which is only appropriate for local use.

## Data Models

### Mailbox
```json
{
  "id": 1,
  "email_address": "test@kupay.site",
  "status": "active",
  "created_at": "2024-01-01T00:00:00Z",
  "expires_at": null
}
```

Mailboxes do not expire: `expires_at` is always `null` and the account stays valid
until it is deleted. Only messages have a retention window (`EMAIL_RETENTION_DAYS`,
30 days): once it passes they are no longer listed or downloadable, and the
retention sweep deletes them and their attachments.

### Message
```json
{
  "id": 1,
  "sender": "sender@example.com",
  "recipient": "test@kupay.site",
  "subject": "Hello",
  "received_at": "2024-01-15T12:00:00Z",
  "is_read": false,
  "attachment_count": 2
}
```

### Attachment
```json
{
  "id": 1,
  "original_filename": "document.pdf",
  "mime_type": "application/pdf",
  "file_size": 102400,
  "created_at": "2024-01-15T12:00:00Z"
}
```

## Implementation Notes

- All timestamps are in UTC ISO 8601 format
- Passwords are never returned by the API
- Sensitive operations require recent authentication
- Attachment downloads are protected by authentication
- Email addresses are case-insensitive
