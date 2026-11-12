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

The repository ships a `docker-compose.yml` with two services: `api` (FastAPI +
Alembic on `/data/dailymail.db`, which also runs the retention sweep on its own
schedule — see Retention Cleanup below) and `web` (nginx serving the built SPA
and proxying `/api`).

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

- The SQLite database lives in the `dailymail-data` volume, used by `api`.
  Back it up with `docker compose exec api sqlite3 /data/dailymail.db ".backup /data/backup.db"`
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
R2 objects are only reclaimed by the retention sweep.

**This runs automatically** inside the API process itself (`app/main.py`, a
background task started at startup) — there is nothing to schedule
separately on any deployment target. By default it sweeps once ~60 seconds
after startup, then every `RETENTION_SWEEP_INTERVAL_HOURS` (24 by default)
for as long as the process runs. Tune it, or turn it off entirely if you'd
rather run it externally instead:

```
RETENTION_SWEEP_ENABLED=true
RETENTION_SWEEP_INTERVAL_HOURS=24
```

A failed sweep (e.g. attachments were due for deletion but R2 is not
configured) is logged and retried on the next cycle; it never crashes the
API process.

### Running it manually or externally instead

The sweep is also a standalone CLI command, useful for an ad-hoc run or if
you'd rather manage scheduling yourself (set `RETENTION_SWEEP_ENABLED=false`
first, so it isn't swept twice — harmless, but redundant):

```bash
cd backend
.venv/bin/python -m app.tasks.retention
```

With cron:

```cron
0 4 * * * cd /home/dailymail/app/backend && .venv/bin/python -m app.tasks.retention >> /var/log/dailymail-retention.log 2>&1
```

Or a systemd timer:

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

The CLI exits with `0` after running. Exit code `1` means expired messages
still held attachments while object storage was not configured: nothing was
deleted, so the next run retries once the R2 credentials are in place.

## Email Provider Setup

Three inbound providers are implemented (`app/providers/`), selected with
`INBOUND_EMAIL_PROVIDER`. **aws_ses is the default and recommended one** —
see why below. forwardemail.net and the Cloudflare Email Worker stay in
the repo as alternatives.

### Why aws_ses, not cloudflare_worker or forward_email

Both alternatives turned out to silently reject mail from some senders
before it ever reaches a routing rule, a Worker, or this app — with no
bounce and nothing in their own logs:

- **Cloudflare Email Routing** rejects at the SMTP level when the sending
  IP is on a third-party RBL it consults (Abusix) — confirmed in
  production with a real sender (VFS Global's OTP emails): even bypassing
  the Worker entirely (`Email Routing` → routing rule → "Send to an
  email" instead of "Send to a Worker"), the message still never arrived.
- **forwardemail.net** runs its own equivalent denylist (UCEPROTECT) and,
  separately, restricts its free plan to a fixed list of TLDs that does
  **not** include `.site` — so `kupay.site` specifically would need a paid
  plan there regardless of the RBL question.

Both are shared infrastructure: thousands of other domains' reputations
share the same receiving pool, so one domain's abuse (or a blocklist
decision Cloudflare/Forward Email didn't make themselves) can silently
cost you mail you never sent and never see. Amazon SES receiving is
pay-per-use (no shared free-tier reputation pool to be collateral damage
of), has no TLD restriction, and its own spam/virus scanning only
*annotates* a verdict on the message by default — it does not reject
delivery unless you explicitly add a rule condition that does. Cost at
personal/friends scale is a few cents a month (SES: **$0.10 per 1,000
messages received + $0.09 per 1,000 "chunks" of 256KB**; S3 and Lambda
costs for this setup are negligible at this volume) — no subscription, no
TLD gate.

### Setting up aws_ses

Architecture: SES receives the mail → a receipt rule stores the raw
message in an S3 bucket and invokes a small Lambda function
(`aws/ses-inbound-forwarder/handler.py`) → the Lambda parses the MIME with
Python's standard library (no dependencies to install) and POSTs the exact
same signed JSON payload the Cloudflare Worker already sends, to the same
webhook, with the same secret → the backend needs **zero new code** for
this (see `app/providers/__init__.py`: `aws_ses` and `cloudflare_worker`
share one implementation).

SES receiving is only available in a few regions — these steps use
**us-east-1 (N. Virginia)**; swap it everywhere if you use a different one.

1. **Create/sign in to an AWS account**, region **us-east-1**.

2. **Verify the domain in SES** (Console → *Simple Email Service* →
   **Configuration → Verified identities** → **Create identity** → *Domain*
   → `kupay.site` → enable **DKIM signing**, keep the default "Easy DKIM").
   SES shows a set of DNS records (DKIM CNAMEs, and an MX if you let it
   manage receiving). Add them at your DNS registrar. Wait for the
   identity's status to flip to **Verified** (can take up to a few hours,
   usually minutes).

3. **Create an S3 bucket** for the raw mail (Console → *S3* → **Create
   bucket**, e.g. `kupay-site-inbound-mail`, same region, block all public
   access — default). Add a bucket policy allowing SES to write to it
   (**Permissions** tab → **Bucket policy**):
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{
       "Sid": "AllowSESPuts",
       "Effect": "Allow",
       "Principal": { "Service": "ses.amazonaws.com" },
       "Action": "s3:PutObject",
       "Resource": "arn:aws:s3:::kupay-site-inbound-mail/*",
       "Condition": { "StringEquals": { "aws:Referer": "<your-aws-account-id>" } }
     }]
   }
   ```

4. **Create the Lambda function** (Console → *Lambda* → **Create
   function** → Author from scratch, name `ses-inbound-forwarder`, runtime
   **Python 3.12**):
   - Paste the entire contents of `aws/ses-inbound-forwarder/handler.py`
     into the inline code editor, replacing the default `lambda_function.py`.
   - **Configuration → General configuration**: set **Handler** to
     `handler.handler` (not the default `lambda_function.lambda_handler`),
     and raise **Timeout** to 15 seconds.
   - **Configuration → Environment variables**:
     ```
     WEBHOOK_URL=https://mail.kupay.site/api/webhooks/inbound-email
     WEBHOOK_SECRET=<generate with: python -c "import secrets; print(secrets.token_urlsafe(32))">
     BUCKET_NAME=kupay-site-inbound-mail
     ```
   - **Configuration → Permissions** → click the execution role → add an
     inline policy granting `s3:GetObject` and `s3:DeleteObject` on
     `arn:aws:s3:::kupay-site-inbound-mail/*`.

5. **Create the SES receipt rule** (Console → SES → **Email receiving** →
   **Create rule set** if you don't have one, then **Create rule**):
   - **Recipient conditions**: add `kupay.site` (matches the whole domain;
     add specific addresses instead if you don't want a catch-all).
   - **Actions**, in this order:
     1. **Deliver to S3 bucket** → the bucket from step 3, no prefix (or
        set one and mirror it in the Lambda's `BUCKET_PREFIX` env var).
     2. **Invoke AWS Lambda function** → the function from step 4.
   - Leave spam/virus handling at its default (annotate, don't reject).
   - **Set as active rule set** (only one rule set is active at a time).

6. **Point DNS at SES** (replace any existing MX record — only one
   receiving system can be active; a sender does not fall back to a
   secondary MX just because the primary rejected the message, only if it
   is fully unreachable):
   ```
   MX    @    inbound-smtp.us-east-1.amazonaws.com    priority 10
   ```

7. Set on the backend:
   ```
   INBOUND_EMAIL_PROVIDER=aws_ses
   INBOUND_WEBHOOK_SECRET=<the same WEBHOOK_SECRET from step 4>
   ```

8. Send a test email, including one with a PDF/image attachment, and
   confirm it shows up. Check the Lambda's **Monitor → Logs** (CloudWatch)
   if it doesn't — a failed webhook POST raises there with the backend's
   actual response, and the raw message stays in S3 (not deleted) until a
   later invocation succeeds, so nothing is lost on a transient failure.

If you want Cloudflare as a pure outage fallback (not a spam-filtering
bypass, which it cannot provide), add it as a secondary MX at a higher
priority number; most senders will never need it.

### Setting up forward_email instead

1. Create a free account at [forwardemail.net](https://forwardemail.net)
   and add the domain — note that the free plan only supports a fixed list
   of TLDs (does **not** include `.site`); a domain outside that list
   needs a paid plan there regardless of the steps below.
2. Set DNS records at the registrar:
   ```
   MX    @    mx1.forwardemail.net    priority 0
   MX    @    mx2.forwardemail.net    priority 0
   TXT   @    <domain verification value Forward Email gives you>
   TXT   @    forward-email=https://<your-public-domain>/api/webhooks/inbound-email?raw=false
   ```
3. Set on the backend: `INBOUND_EMAIL_PROVIDER=forward_email`. No secret to
   configure: the free plan has no HMAC signing key, so this provider
   verifies deliveries by resolving the caller's IP via reverse DNS and
   checking it resolves to `mx1.forwardemail.net` or `mx2.forwardemail.net`.
4. Send a test email with an attachment and confirm it shows up.

### Setting up cloudflare_worker instead

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
6. Set on the backend:
   ```
   INBOUND_EMAIL_PROVIDER=cloudflare_worker
   INBOUND_WEBHOOK_SECRET=<the secret from step 3>
   ```

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

**aws_ses:**
- Check SES → **Email receiving** → your rule set is **active** and its
  recipient condition actually matches the address used
- Check the Lambda's **Monitor → Logs** (CloudWatch) for the invocation —
  an exception there means the webhook POST failed; the raw message stays
  in the S3 bucket (not deleted) so no retry is needed once the real cause
  (wrong `WEBHOOK_SECRET`, wrong `WEBHOOK_URL`, backend down) is fixed
- Verify `INBOUND_WEBHOOK_SECRET` on the backend matches `WEBHOOK_SECRET`
  on the Lambda exactly
- Confirm the MX record actually points at `inbound-smtp.<region>.amazonaws.com`
  and no other MX record is still active for the domain

**cloudflare_worker:**
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
