# DailyMail

A private temporary email service for personal use and sharing with a small group of friends.

## Overview

DailyMail allows users to create temporary email addresses, receive messages, manage attachments, and administer everything through a dashboard.

- **Domain**: `kupay.site`
- **Frontend**: `mail.kupay.site`
- **Message Retention**: 30 days (mailbox accounts persist until deleted)

## Architecture

| Component | Technology |
|---|---|
| Frontend | React + TypeScript + Tailwind CSS |
| Backend | Python + FastAPI |
| Database | SQLite |
| Attachment Storage | Cloudflare R2 |
| Frontend Hosting | Cloudflare Pages |
| Email Reception | Cloudflare Email Workers + Email Routing |
| Email Domain | Cloudflare Nameservers |

## Project Structure

```
dailymail/
├── backend/           # Python FastAPI backend
│   ├── app/
│   │   ├── api/       # API routes
│   │   ├── core/      # Configuration and database
│   │   ├── models/    # SQLAlchemy models
│   │   ├── schemas/   # Pydantic schemas
│   │   ├── services/  # Business logic
│   │   ├── providers/ # External provider abstractions
│   │   ├── storage/   # Storage providers
│   │   ├── tasks/     # Background tasks
│   │   └── main.py    # FastAPI application
│   ├── migrations/    # Alembic migrations
│   ├── tests/         # Test suite
│   └── requirements.txt
├── frontend/          # React TypeScript frontend
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── services/
│   │   ├── hooks/
│   │   ├── layouts/
│   │   ├── types/
│   │   └── App.tsx
│   └── package.json
├── docs/              # Documentation
│   ├── ARCHITECTURE.md
│   ├── API.md
│   └── DEPLOYMENT.md
└── README.md
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

## Features (Planned)

### Phase 1: Foundation (Current)
- ✅ Project structure
- ✅ Database models
- ✅ FastAPI setup
- ✅ React setup with routing

### Phase 2: Mailboxes and Authentication
- ✅ Individual email creation
- ✅ Batch email creation
- ✅ Password-based authentication
- ✅ Token sessions (short-lived JWT)

### Phase 3: Email Reception
- ✅ Signed webhook (HMAC-SHA256, replay window)
- ✅ Cloudflare Email Worker (`worker/`)
- ✅ Message storage with duplicate protection and HTML sanitisation
- ✅ Inbox interface (frontend)

### Phase 4: Attachments
- ✅ Cloudflare R2 integration (S3-compatible API via boto3)
- ✅ Attachment forwarding from the Email Worker
- ✅ Allow-list, signature check and size limits
- ✅ Authenticated downloads and inline preview for PDF/images
- ⬜ Validation against a real R2 bucket (requires credentials)

### Phase 5: Administration
- ✅ Admin dashboard (`/api/admin/dashboard` and the `/admin` screen)
- ✅ Mailbox management (search, filter, block/activate, soft delete)
- ✅ Batch management (list, shared password reset)
- ✅ Message and attachment management (search, delete with storage cleanup)
- ✅ Admin actions written to the audit log

### Phase 6: Retention and Security
- ✅ Expired messages hidden from the API and purged with their R2 objects (`python -m app.tasks.retention`, run from cron)
- ✅ Individual message deletion removes its stored attachments
- ✅ Rate limiting on creation and login, plus optional creation secret
- ✅ Separate mailbox/admin token scopes and Argon2id passwords
- ⬜ Security hardening review
- ✅ Test suite (backend)

### Phase 7: Deployment
- ✅ Production configuration (env vars, single-worker SQLite, retention schedule)
- ✅ Containerization (`backend/Dockerfile`, `frontend/Dockerfile`, `docker-compose.yml`)
- ✅ Documentation (`docs/`)

## Documentation

See the `docs/` folder for detailed documentation:
- [Architecture](docs/ARCHITECTURE.md)
- [API Reference](docs/API.md)
- [Deployment Guide](docs/DEPLOYMENT.md)

## Security

- All passwords are hashed with Argon2id
- Webhook signatures are validated
- Attachment uploads are restricted by type and size
- Admin operations are logged
- Temporary access tokens with expiration

## License

Private project

## Contributing

Development is ongoing. See the implementation specification for details.
