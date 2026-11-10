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

ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=<argon2id-hash>
ADMIN_API_SECRET=<random-secret>

R2_ACCOUNT_ID=<your-account-id>
R2_ACCESS_KEY_ID=<your-key>
R2_SECRET_ACCESS_KEY=<your-secret>
R2_BUCKET_NAME=dailymail-attachments

INBOUND_EMAIL_PROVIDER=<provider>
INBOUND_WEBHOOK_SECRET=<webhook-secret>

ACCESS_TOKEN_SECRET=<random-secret>
```

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

#### Option 2: Docker

(To be implemented)

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

- [ ] Generate new ADMIN_PASSWORD_HASH and ADMIN_API_SECRET
- [ ] Configure HTTPS/SSL certificates
- [ ] Set strong ACCESS_TOKEN_SECRET
- [ ] Configure CORS for known domains only
- [ ] Enable rate limiting
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
