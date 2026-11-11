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
4. **Stateless API**: Sessions via tokens, not server-side state
5. **Simple but Scalable**: SQLite for MVP, easy migration to PostgreSQL later

## Database Schema

### Core Tables

#### mailboxes
- Represents a temporary email address
- Linked to a batch (optional)
- Password protected with Argon2id
- Status: active, blocked, deleted

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
- Email + password based
- Generates short-lived JWT token
- Token included in subsequent requests

### Admin Access
- Username + password with Argon2id hashing
- Separate admin token
- All admin actions logged

## Storage

### Attachment Storage
- Files stored in Cloudflare R2
- Database stores only metadata and reference key
- Downloads use signed/authenticated URLs
- File names randomized for security

## External Integrations

### Cloudflare Email Workers
- Cloudflare Email Routing receives emails for kupay.site
- Cloudflare Email Worker (serverless function) processes incoming emails
- Worker converts MIME email to JSON payload
- Worker POSTs to FastAPI webhook endpoint
- FastAPI validates and stores message + attachments
- No provider abstraction needed (dedicated Email Worker)

## Security Measures

1. **Password Storage**: Argon2id hashing
2. **Rate Limiting**: Applied to authentication endpoints
3. **CORS**: Restricted to known frontend domains
4. **Input Validation**: Pydantic schemas for all inputs
5. **SQL Injection**: Protected via SQLAlchemy ORM
6. **XSS Prevention**: HTML content sanitized before storage
7. **Path Traversal**: Filenames never used directly in paths
8. **Webhook Validation**: Signature verification before processing
9. **Token Expiration**: Short-lived access tokens
10. **Audit Logging**: Admin actions recorded

## Scalability Considerations

### Current (MVP)
- SQLite database
- Single process backend
- File-based storage simulation

### Future Improvements
- PostgreSQL for production
- Multi-process/multi-server backend
- Redis for caching and rate limiting
- Cloudflare R2 for production storage
- Message queue for background jobs

## Error Handling

- Consistent error response format
- No sensitive information in error messages
- Webhook failures retried (TBD)
- Transaction rollback on database errors
