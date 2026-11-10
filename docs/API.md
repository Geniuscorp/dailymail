# DailyMail API Documentation

## Overview

Base URL: `http://localhost:8000/api` (development)
Base URL: `https://api.kupay.site/api` (production)

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
  "expires_in": 86400
}
```

Include token in Authorization header:
```
Authorization: Bearer <token>
```

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
  "email_address": "user@example.com",
  "password": "secure_password"
}
```

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
- `is_read`: filter by read status

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
```

Returns file content with appropriate Content-Type.

### Webhooks

#### Inbound Email
```
POST /webhooks/inbound-email
```

Webhook from email provider. Signature validation required.

Provider-specific format. Consult provider documentation.

### Admin Endpoints

#### Admin Login
```
POST /admin/login
```

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
- `status`: filter by status
- `limit`: number per page
- `offset`: pagination

#### List Batches
```
GET /admin/batches
```

#### Manage Mailboxes
```
PATCH /admin/mailboxes/{mailbox_id}
PATCH /admin/batches/{batch_id}/password
DELETE /admin/mailboxes/{mailbox_id}
```

#### Manage Messages
```
GET /admin/messages
DELETE /admin/messages/{message_id}
```

#### Manage Attachments
```
GET /admin/attachments
DELETE /admin/attachments/{attachment_id}
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
- `422`: Validation Error
- `500`: Server Error

## Rate Limiting

(To be implemented in Phase 6)

- Authentication endpoints: 10 requests per minute per IP
- Message access: 1000 requests per hour per token
- Admin endpoints: 100 requests per hour per token

## Data Models

### Mailbox
```json
{
  "id": 1,
  "email_address": "test@kupay.site",
  "status": "active",
  "created_at": "2024-01-01T00:00:00Z",
  "expires_at": "2024-01-31T00:00:00Z"
}
```

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
