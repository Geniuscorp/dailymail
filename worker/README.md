# DailyMail Email Worker

Cloudflare Email Worker that receives mail for `kupay.site` through Email Routing, converts it to JSON and forwards it, signed with HMAC-SHA256, to the FastAPI webhook `POST /api/webhooks/inbound-email`.

## Contract

Signed string: `"<timestamp>.<raw JSON body>"`, HMAC-SHA256 with `INBOUND_WEBHOOK_SECRET`.

Headers: `X-DailyMail-Timestamp` (unix seconds), `X-DailyMail-Signature` (hex).

Body fields: `message_id`, `sender`, `recipient`, `subject`, `text`, `html`, `received_at`.

The backend rejects deliveries older than `INBOUND_WEBHOOK_TOLERANCE_SECONDS` (default 300).

## Setup

1. Install dependencies:

   ```bash
   cd worker
   npm install
   ```

2. Set the backend URL in `wrangler.toml` (`BACKEND_URL`).

3. Store the shared secret (must equal the backend's `INBOUND_WEBHOOK_SECRET`):

   ```bash
   npx wrangler secret put INBOUND_WEBHOOK_SECRET
   ```

4. Deploy:

   ```bash
   npx wrangler deploy
   ```

5. In the Cloudflare dashboard for `kupay.site`, enable **Email Routing**, add the destination/catch-all rule `*@kupay.site` → this Worker. This changes DNS MX records and must be done deliberately by the domain owner.

## Limitations

- Attachments are not forwarded yet (Phase 4 adds R2 storage).
- Messages larger than 10 MB are rejected at the SMTP level.
- If the backend returns 5xx, the Worker throws so the sending server retries; 4xx responses reject the message.
