# DailyMail

A private temporary email service for personal use and sharing with a small group of friends — create an address with a password, receive mail instantly, and never think about it again.

## Overview

DailyMail lets anyone create a temporary `@kupay.site` address protected by a password, read incoming mail (text, HTML and attachments) the moment it arrives, and manage the account themselves — no admin intervention needed for day-to-day use.

- **Domain**: `kupay.site`
- **Frontend**: `mail.kupay.site`
- **Message retention**: 30 days (mailbox accounts persist until the owner deletes them)
- **Sessions**: a password is only needed at account creation and at login — after that, an opaque, revocable session (not a JWT) keeps the browser signed in for 90 days, like mail.tm

## Architecture

| Component | Technology |
|---|---|
| Frontend | React + TypeScript + Tailwind CSS |
| Backend | Python + FastAPI |
| Database | SQLite |
| Attachment Storage | Cloudflare R2 |
| Email Reception | forwardemail.net (default) or Cloudflare Email Routing + Worker (`worker/`, alternative) — see docs/ARCHITECTURE.md |
| Email Domain | Cloudflare Nameservers |
| Deployment | Docker Compose (`api` + `web`), nginx serving the SPA and proxying `/api` same-origin |

## Project Structure

```
dailymail/
├── backend/           # Python FastAPI backend
│   ├── app/
│   │   ├── api/       # API routes
│   │   ├── core/      # Configuration, database, auth, rate limiting, SSE broker
│   │   ├── models/    # SQLAlchemy models
│   │   ├── schemas/   # Pydantic schemas
│   │   ├── services/  # Business logic
│   │   ├── providers/ # External provider abstractions
│   │   ├── storage/   # Storage providers (R2)
│   │   ├── tasks/     # Background tasks (retention sweep)
│   │   └── main.py    # FastAPI application
│   ├── migrations/    # Alembic migrations
│   ├── tests/         # Test suite
│   └── requirements.txt
├── frontend/          # React TypeScript frontend
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── services/
│   │   ├── layouts/
│   │   ├── types/
│   │   └── App.tsx
│   ├── nginx.conf.template
│   └── package.json
├── worker/            # Cloudflare Email Worker (receives mail, signs and forwards it)
├── scripts/           # Operational scripts (e.g. verify-inbound.sh)
├── docs/              # Documentation
│   ├── ARCHITECTURE.md
│   ├── API.md
│   └── DEPLOYMENT.md
└── docker-compose.yml
```

## Development Setup

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

## Features

### Mailboxes and sessions
- ✅ Self-service account creation from the site (`/create`), with automatic login
- ✅ Individual and batch email creation via the API
- ✅ Password-based authentication; Argon2id hashing
- ✅ Persistent, revocable sessions (opaque tokens stored hashed in `mailbox_sessions`, not JWT) — survive browser restarts, valid 90 days by default
- ✅ Logout revokes only the current session; a password change revokes every *other* session; deleting the account revokes all of them
- ✅ Self-service settings (`/account`): change password, delete account
- ✅ Quick account switcher (create or log into another mailbox without leaving the page)

### Email reception
- ✅ Signed webhook (HMAC-SHA256, replay window) between the Cloudflare Email Worker and the API
- ✅ Message storage with duplicate protection and HTML sanitisation (XSS-safe, sandboxed rendering)
- ✅ Real-time inbox: new mail is pushed to the browser over Server-Sent Events the instant it is stored, with a slow fallback poll as a safety net — no manual refresh needed
- ✅ Attachments: PDFs, images and common office/archive formats, validated by file signature (not by the sender's claimed type), stored in Cloudflare R2
- ✅ Best-effort attachment delivery: a storage failure or unconfigured R2 drops just that attachment, never the whole message
- ✅ Retention sweep runs automatically inside the API process itself (no separate cron job or container to configure on any deployment target)

### Administration
- ✅ Admin dashboard (`/api/admin/dashboard` and the `/admin` screen, kept out of the main navigation)
- ✅ Mailbox management (search, filter, block/activate, soft delete)
- ✅ Batch management (list, shared password reset)
- ✅ Message and attachment management (search, delete with storage cleanup)
- ✅ Every admin action written to an audit log

### Security
- ✅ Rate limiting on creation, login and the inbound webhook, plus an optional creation secret
- ✅ Separate mailbox/admin token scopes; the app refuses to start in production with a missing or placeholder `ACCESS_TOKEN_SECRET`
- ✅ Configurable CORS allow-list (`CORS_ALLOWED_ORIGINS`), no hardcoded domain
- ✅ Correct client-IP attribution behind the bundled nginx proxy, so the rate limiter can't be bypassed or turned into a shared budget for every visitor
- ✅ Test suite (backend): 117+ tests covering auth, sessions, attachments, webhooks, retention and the SSE push

### Deployment
- ✅ Production configuration (env vars, single-worker SQLite, retention schedule)
- ✅ Containerization (`backend/Dockerfile`, `frontend/Dockerfile`, `docker-compose.yml`)
- ✅ Documentation (`docs/`)

## Documentation

See the `docs/` folder for detailed documentation:
- [Architecture](docs/ARCHITECTURE.md)
- [API Reference](docs/API.md)
- [Deployment Guide](docs/DEPLOYMENT.md)

Interactive API docs (Swagger UI) are also served live at `/docs` on the same domain as the site.

## Security

- All passwords are hashed with Argon2id
- Webhook signatures are validated (HMAC-SHA256, with a replay-tolerance window)
- Mailbox sessions are opaque, hashed at rest, and individually revocable
- Attachment uploads are restricted by allow-listed type and size, verified by file signature
- Admin operations are logged
- Production refuses to boot with an insecure or missing token secret

## License

Private project

## Contributing

Development is ongoing. See the `docs/` folder for architecture and API details before making changes.
