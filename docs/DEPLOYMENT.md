# DailyMail Deployment Guide

## Prerequisites

- Python 3.11+
- Node.js 18+
- A Cloudflare account for the domain (`kupay.site`), with:
  - **R2** enabled (attachment storage)
  - **Email Routing** enabled (inbound mail → the Email Worker in `worker/`)
- Domain DNS on Cloudflare Nameservers

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
CORS_ALLOWED_ORIGINS=https://mail.kupay.site,http://localhost:3000,http://localhost:5173

ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=<argon2id-hash>

R2_ACCOUNT_ID=<your-account-id>
R2_ACCESS_KEY_ID=<your-key>
R2_SECRET_ACCESS_KEY=<your-secret>
R2_BUCKET_NAME=dailymail-attachments

INBOUND_EMAIL_PROVIDER=cloudflare_worker
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

2. Configure API endpoint. Leave it empty for the same-origin setup used by
   `docker-compose.yml`/the Northflank combined service (nginx proxies `/api`
   to the backend on the same domain); set it only if the API is genuinely on
   its own domain (e.g. the VPS option below):

```
VITE_API_BASE_URL=
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

    # nginx's own default (1MB) is well under MAX_INBOUND_PAYLOAD_MB (40MB):
    # without this, nginx rejects any inbound-email delivery carrying an
    # attachment with its own 413 before the app ever sees the request.
    client_max_body_size 45M;

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
- `VITE_MAIL_DOMAIN` (also a build argument, default `kupay.site`) is shown as the
  fixed `@domain` suffix on the "create account" form; keep it in sync with the
  backend's `DOMAIN` setting.

### Frontend Deployment

#### Cloudflare Pages

1. Build the project:

```bash
npm run build
```

2. Connect repository to Cloudflare Pages:
   - Build command: `npm run build`
   - Build output directory: `dist`

3. Configure domain: `mail.kupay.site`

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

Inbound mail is handled entirely by Cloudflare: **Email Routing** receives
it for the domain and hands it to a dedicated **Email Worker**
(`worker/`), which converts the MIME message to JSON, signs it, and POSTs
it to `POST /api/webhooks/inbound-email`. There is no provider abstraction
to swap here by design — see `worker/README.md` for the exact contract.

1. Install and configure the Worker (full steps in `worker/README.md`):
   ```bash
   cd worker
   npm install
   ```
2. Set `BACKEND_URL` in `worker/wrangler.toml` to the site's real public
   origin. With the Docker Compose / combined-service deployment this is
   the **same domain the browser uses** (nginx proxies `/api` internally) —
   there is no separate `api.*` subdomain unless you deploy the API as its
   own publicly reachable service.
3. Store the shared secret (must equal the backend's `INBOUND_WEBHOOK_SECRET`):
   ```bash
   npx wrangler secret put INBOUND_WEBHOOK_SECRET
   ```
4. Deploy:
   ```bash
   npx wrangler deploy
   ```
5. In the Cloudflare dashboard for the domain: **Email** → **Email Routing**
   → **Enable Email Routing** (this adds the MX records automatically) →
   add a routing rule, `*@kupay.site` (or specific addresses) → **Send to a
   Worker** → the Worker deployed above.

A bounce from the receiving mail server citing a `4xx`/`5xx` and a status
code (e.g. `"Delivery rejected by backend (413)"`) means the **Worker**
got a non-2xx from the API — check the backend logs for that status code
first; a `413` almost always means `client_max_body_size` in nginx (see
below), not the application's own `MAX_INBOUND_PAYLOAD_MB`.

## Cloudflare R2 Setup

Without this configured, inbound attachments are silently dropped (the
message itself is still delivered and stored — see
[Architecture](ARCHITECTURE.md#attachment-storage)).

1. Cloudflare dashboard → account level (not inside the domain's settings)
   → **R2 Object Storage**. First use requires accepting the R2
   subscription (free up to 10GB storage / 1M Class A / 10M Class B
   operations per month — comfortably above personal use; you are only
   billed past that).
2. **Create bucket**, name: `dailymail-attachments`, location: Automatic.
3. **Manage R2 API Tokens** → **Create API Token**:
   - Permissions: **Object Read & Write**
   - Specify bucket(s): `dailymail-attachments`
   - On creation, Cloudflare shows the **Access Key ID** and **Secret
     Access Key** exactly once — save them immediately.
4. The **Account ID** is shown on the R2 overview page (or in the
   dashboard's URL).
5. Set on the backend service's environment:
   ```
   R2_ACCOUNT_ID=<account-id>
   R2_ACCESS_KEY_ID=<access-key-id>
   R2_SECRET_ACCESS_KEY=<secret-access-key>
   R2_BUCKET_NAME=dailymail-attachments
   ```
   Double-check the variable *names* exactly — a typo (e.g.
   `R2_SECRET_ACCESS` missing `_KEY`) leaves the field unset with no
   startup error; `get_object_storage()` just treats R2 as unconfigured.
6. Restart the backend service so it picks up the new variables.

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
- [ ] Set a real, 32+ character ACCESS_TOKEN_SECRET (production refuses to boot without one)
- [ ] Set CORS_ALLOWED_ORIGINS to the frontend's actual live domain(s), comma-separated
- [ ] Set RATE_LIMIT_ENABLED=true and tune the per-minute limits
- [ ] Set MAILBOX_CREATION_SECRET and use the header when creating mailboxes
- [ ] Confirm `--forwarded-allow-ips` is set correctly for the actual proxy topology (see Docker Compose notes below) — otherwise the rate limiter becomes one shared budget for every visitor
- [ ] Set `client_max_body_size` in nginx above `MAX_INBOUND_PAYLOAD_MB` (nginx's own default of 1MB otherwise blocks any email with an attachment)
- [ ] Configure firewall rules
- [ ] Setup monitoring and logging
- [ ] Backup database regularly
- [ ] Configure email provider webhook validation
- [ ] Test webhook delivery, including one with an attachment
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

- Check the Cloudflare Worker's logs (dashboard → Workers & Pages → the
  Worker → Logs) for the actual response status the backend returned
- A bounce naming a status code (e.g. `"rejected by backend (413)"`) means
  the backend rejected the Worker's request — check `client_max_body_size`
  in nginx first for a `413` (see Cloudflare R2 Setup / Email Provider
  Setup above), then the backend logs for anything else
- Verify `BACKEND_URL` in `worker/wrangler.toml` actually points at the
  live public origin (redeploy with `npx wrangler deploy` after changing it)
- Verify `INBOUND_WEBHOOK_SECRET` matches on both sides
- Confirm the Email Routing rule actually points at this Worker

### Attachment upload fails / attachments are missing from a message

- A missing R2 configuration or a storage failure no longer fails the
  whole delivery — the message arrives without that attachment. Check the
  backend logs for a line like `attachment storage not configured;
  dropping '<filename>'` or `failed to store attachment`
- Check the 4 `R2_*` variable **names** are exactly right (a typo leaves
  the value unset with no startup error)
- Verify the bucket name matches `R2_BUCKET_NAME`
- Check `MAX_ATTACHMENT_SIZE_MB` / `MAX_ATTACHMENTS_PER_MESSAGE`
