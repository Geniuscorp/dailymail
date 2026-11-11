# DailyMail Deployment Guide

## Prerequisites

- Python 3.11+
- Node.js 18+
- Cloudflare account with R2 enabled
- Email provider account (to be selected)
- Domain DNS configured (kupay.site)

## Environment Configuration

### Backend

1. Copy `.env.example` to `.env` in `backend/`:

```bash
cp backend/.env.example backend/.env
```

2. Configure required variables:

```
DATABASE_URL=sqlite:///./dailymail.db
DOMAIN=kupay.site
# Must match the real URL the frontend is served from right now, not the
# final domain if it isn't live yet (e.g. a Cloudflare Pages preview URL,
# a VPS IP, or http://localhost:5173 during local testing).
CORS_ALLOWED_ORIGINS=https://temp.kupay.site,http://localhost:3000,http://localhost:5173

ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=<argon2id-hash>

R2_ACCOUNT_ID=<your-account-id>
R2_ACCESS_KEY_ID=<your-key>
R2_SECRET_ACCESS_KEY=<your-secret>
R2_BUCKET_NAME=dailymail-attachments

INBOUND_EMAIL_PROVIDER=<provider>
INBOUND_WEBHOOK_SECRET=<webhook-secret>

# Required in production; the app refuses to start without a real value here
# (at least 32 chars, not the placeholder from .env.example).
ACCESS_TOKEN_SECRET=<random-secret>
MAILBOX_SESSION_EXPIRE_DAYS=90

RATE_LIMIT_ENABLED=true
RATE_LIMIT_CREATE_PER_MINUTE=10
RATE_LIMIT_LOGIN_PER_MINUTE=10
RATE_LIMIT_WEBHOOK_PER_MINUTE=120
MAILBOX_CREATION_SECRET=<random-secret>
```

`MAILBOX_CREATION_SECRET` is what stops strangers from creating mailboxes on your
domain: when it is set, `POST /api/mailboxes` and `POST /api/mailboxes/batch`
require the `X-DailyMail-Creation-Secret` header. Mailbox accounts never expire;
only message content has a 30-day window.

### Mailbox sessions

A password is only needed twice: at `POST /api/mailboxes` (creation) and at
`POST /api/mailboxes/login`. Login returns an opaque, long-lived session token
(`MAILBOX_SESSION_EXPIRE_DAYS`, 90 days by default) that is stored hashed in
the `mailbox_sessions` table — not a JWT, so it can be looked up and revoked.
The frontend keeps the raw token in `localStorage`, so the inbox stays open
across browser restarts like mail.tm, until the user logs out
(`POST /api/mailboxes/logout`, revokes only that session), changes the
password (revokes every *other* session), or deletes the mailbox (revokes
all of them).

### Frontend

1. Copy `.env.example` to `.env` in `frontend/`:

```bash
cp frontend/.env.example frontend/.env
```

2. Configure API endpoint:

```
VITE_API_BASE_URL=https://api.kupay.site
```

## Local Development

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Backend will be available at `http://localhost:8000`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend will be available at `http://localhost:3000`

## Production Deployment

### Backend Deployment Options

#### Option 1: VPS (Recommended for MVP)

1. Install dependencies:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. Create systemd service (`/etc/systemd/system/dailymail-api.service`):

```ini
[Unit]
Description=DailyMail API
After=network.target

[Service]
Type=notify
User=dailymail
WorkingDirectory=/home/dailymail/app
Environment="PATH=/home/dailymail/app/venv/bin"
ExecStart=/home/dailymail/app/venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

[Install]
WantedBy=multi-user.target
```

3. Enable and start:

```bash
sudo systemctl enable dailymail-api
sudo systemctl start dailymail-api
```

4. Configure nginx as reverse proxy:

```nginx
server {
    listen 443 ssl http2;
    server_name api.kupay.site;
    
    ssl_certificate /etc/letsencrypt/live/kupay.site/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/kupay.site/privkey.pem;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

#### Option 2: Docker Compose

The repository ships a `docker-compose.yml` with three services: `api` (FastAPI +
Alembic on `/data/dailymail.db`), `web` (nginx serving the built SPA and proxying
`/api`) and `retention` (the daily retention sweep).

1. Create `backend/.env` from `backend/.env.example` and fill in the secrets. Set
   `RATE_LIMIT_ENABLED=true` and a `MAILBOX_CREATION_SECRET`, and leave
   `DATABASE_URL` out (Compose points it at the volume):

   ```bash
   cp backend/.env.example backend/.env
   ```

2. Build and start:

   ```bash
   docker compose up -d --build
   ```

3. The site is served on `http://localhost:8080` (put TLS in front of it with a
   reverse proxy). The API is only reachable inside the Compose network; the SPA
   calls `/api` on the same origin, which nginx forwards to `api:8000`.

4. Check it is alive:

   ```bash
   docker compose ps
   docker compose exec web wget -qO- http://localhost/ >/dev/null && echo web ok
   docker compose logs --tail=50 api
   ```

Notes:

- The SQLite database lives in the `dailymail-data` volume, shared by `api` and
  `retention`. Back it up with `docker compose exec api sqlite3 /data/dailymail.db ".backup /data/backup.db"`
  and copy the file out.
- The API runs a single uvicorn worker: SQLite has one writer and the rate limiter
  is per process. Do not scale `api` horizontally without moving both out.
- The `api` container trusts `X-Forwarded-For` from any address
  (`--forwarded-allow-ips='*'` in `backend/Dockerfile`). That is safe only
  because `api` publishes no port of its own and is reachable exclusively from
  the `web` (nginx) container on the Compose network — if you ever expose
  `api`'s port directly, remove that flag first or the rate limiter can be
  trivially bypassed by spoofing the header.
- Alembic runs on every `api` start, so schema upgrades ship with the image.
- To change the public URL of the API instead of using the same-origin proxy, pass
  `VITE_API_BASE_URL` as a build argument (it is compiled into the bundle).

### Frontend Deployment

#### Cloudflare Pages

1. Build the project:

```bash
npm run build
```

2. Connect repository to Cloudflare Pages:
   - Build command: `npm run build`
   - Build output directory: `dist`

3. Configure domain: `temp.kupay.site`

## Database Migrations

### Initial Setup

```bash
cd backend
alembic upgrade head
```

### Creating Migrations

After modifying models:

```bash
alembic revision --autogenerate -m "Description"
alembic upgrade head
```

## Retention Cleanup

Messages become unreadable through the API as soon as they pass their retention
window (`EMAIL_RETENTION_DAYS`, 30 days by default), but the database rows and the
R2 objects are only reclaimed by the retention sweep:

```bash
cd backend
.venv/bin/python -m app.tasks.retention
```

Run it daily, for example with cron:

```cron
0 4 * * * cd /home/dailymail/app/backend && .venv/bin/python -m app.tasks.retention >> /var/log/dailymail-retention.log 2>&1
```

or with a systemd timer:

```ini
# /etc/systemd/system/dailymail-retention.service
[Unit]
Description=DailyMail retention sweep

[Service]
Type=oneshot
User=dailymail
WorkingDirectory=/home/dailymail/app/backend
Environment="PATH=/home/dailymail/app/backend/venv/bin"
ExecStart=/home/dailymail/app/backend/venv/bin/python -m app.tasks.retention

# /etc/systemd/system/dailymail-retention.timer
[Unit]
Description=Run the DailyMail retention sweep daily

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
```

The sweep exits with `0` after running. Exit code `1` means expired messages still
held attachments while object storage was not configured: nothing was deleted, so
the next run retries once the R2 credentials are in place.

## Email Provider Setup

(Provider-specific steps to be documented once provider is selected)

## Cloudflare R2 Setup

1. Create bucket: `dailymail-attachments`

2. Generate API token with S3 access

3. Store credentials in environment variables

4. (Optional) Configure CORS for direct uploads

## Monitoring

### Backend Logs

```bash
journalctl -u dailymail-api -f
```

### Database Backups

```bash
sqlite3 dailymail.db ".backup backup.db"
```

## Scaling Considerations

### Current Limitations (MVP)

- Single SQLite database (concurrent write issues)
- Single-process backend
- Local file storage simulation

### Migration Path

1. **PostgreSQL**: Better concurrency and reliability
2. **Redis**: Caching and rate limiting
3. **Message Queue**: Background job processing
4. **Load Balancer**: Multiple backend instances
5. **CDN**: Static asset caching

## Security Checklist

- [ ] Generate new ADMIN_PASSWORD_HASH
- [ ] Configure HTTPS/SSL certificates
- [ ] Set strong ACCESS_TOKEN_SECRET
- [ ] Configure CORS for known domains only
- [ ] Set RATE_LIMIT_ENABLED=true and tune the per-minute limits
- [ ] Set MAILBOX_CREATION_SECRET and use the header when creating mailboxes
- [ ] Configure firewall rules
- [ ] Setup monitoring and logging
- [ ] Backup database regularly
- [ ] Configure email provider webhook validation
- [ ] Test webhook delivery
- [ ] Review and harden nginx configuration

## Troubleshooting

### Backend fails to start

- Check `.env` configuration
- Verify database permissions
- Check port 8000 availability

### Frontend build fails

- Clear node_modules: `rm -rf node_modules && npm install`
- Check Node.js version: `node -v`

### Email not received

- Check webhook configuration
- Verify INBOUND_WEBHOOK_SECRET
- Review provider logs
- Test provider webhook delivery

### Attachment upload fails

- Check R2 credentials
- Verify bucket name
- Check file size limits
- Review R2 CORS configuration
