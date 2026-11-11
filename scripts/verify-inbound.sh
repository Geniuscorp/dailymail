#!/usr/bin/env bash
# Checks that everything needed to receive email from the internet is in place.
#
#   ./scripts/verify-inbound.sh <BASE_URL> [DOMAIN] [MAILBOX_ADDRESS]
#
# Example:
#   ./scripts/verify-inbound.sh https://api.kupay.site kupay.site eu@kupay.site
#
# Reads INBOUND_WEBHOOK_SECRET from the environment, falling back to backend/.env.
# MAILBOX_PASSWORD is optional; when set, the script logs in and confirms the
# delivered message is visible through the API.
#
# Exit code 0 means every required check passed. MX records are required for
# real delivery, so a missing MX is a failure, not a warning.

set -uo pipefail

BASE="${1:-}"
DOMAIN="${2:-kupay.site}"
MAILBOX="${3:-}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BODY="$(mktemp)"
trap 'rm -f "$BODY"' EXIT

if [ -z "$BASE" ]; then
  echo "usage: $0 <BASE_URL> [DOMAIN] [MAILBOX_ADDRESS]" >&2
  exit 2
fi
BASE="${BASE%/}"

for bin in curl openssl; do
  command -v "$bin" >/dev/null || { echo "missing dependency: $bin" >&2; exit 2; }
done

if [ -z "${INBOUND_WEBHOOK_SECRET:-}" ] && [ -f "$ROOT/backend/.env" ]; then
  INBOUND_WEBHOOK_SECRET="$(grep -E '^INBOUND_WEBHOOK_SECRET=' "$ROOT/backend/.env" | head -1 | cut -d= -f2-)"
fi
INBOUND_WEBHOOK_SECRET="${INBOUND_WEBHOOK_SECRET:-}"

pass=0; fail=0
ok()   { pass=$((pass + 1)); printf '  PASS  %s\n' "$1"; }
bad()  { fail=$((fail + 1)); printf '  FAIL  %s\n' "$1"; [ -n "${2:-}" ] && printf '        %s\n' "$2"; }
note() { printf '        %s\n' "$1"; }

http_code() { curl -s -o /dev/null -m 20 -w '%{http_code}' "$@"; }

echo "DailyMail inbound readiness — $BASE (domain: $DOMAIN)"
echo

echo "1. Backend reachable over this URL"
code="$(http_code "$BASE/health")"
if [ "$code" = "200" ]; then
  ok "GET $BASE/health -> 200"
else
  bad "GET $BASE/health -> $code" "Cloudflare cannot POST to a backend it cannot reach. Check the host, TLS and the reverse proxy."
fi

echo
echo "2. Webhook rejects unauthenticated payloads"
code="$(http_code -X POST "$BASE/api/webhooks/inbound-email" -H 'Content-Type: application/json' -d '{"message_id":"probe"}')"
if [ "$code" = "401" ]; then
  ok "unsigned POST -> 401"
elif [ "$code" = "000" ]; then
  bad "unsigned POST -> no response" "Endpoint unreachable."
else
  bad "unsigned POST -> $code" "Expected 401. An endpoint accepting unsigned payloads is exposed to forged mail."
fi

echo
echo "3. MX records for $DOMAIN (required for internet mail)"
if command -v dig >/dev/null; then
  mx="$(dig +short MX "$DOMAIN" @1.1.1.1)"
  if [ -z "$mx" ]; then
    bad "no MX records for $DOMAIN" "Enable Email Routing in the Cloudflare dashboard for this zone; it publishes the MX records."
  elif printf '%s' "$mx" | grep -qi 'mx.cloudflare.net'; then
    ok "MX points to Cloudflare Email Routing"
    printf '%s\n' "$mx" | sed 's/^/        /'
  else
    bad "MX does not point to Cloudflare" "Real mail will not reach the Worker. Current records:"
    printf '%s\n' "$mx" | sed 's/^/        /'
  fi
  ns="$(dig +short NS "$DOMAIN" @1.1.1.1 | head -2)"
  if printf '%s' "$ns" | grep -qi 'ns.cloudflare.com'; then
    ok "nameservers are Cloudflare"
  else
    bad "nameservers are not Cloudflare: $(printf '%s' "$ns" | tr '\n' ' ')" "Move the domain to Cloudflare first; Email Routing only works on Cloudflare zones."
  fi
else
  note "dig not installed, skipping DNS checks"
fi

echo
echo "4. Signed delivery (same request the Worker sends)"
if [ -z "$INBOUND_WEBHOOK_SECRET" ]; then
  bad "INBOUND_WEBHOOK_SECRET not set" "Export it or put it in backend/.env; it must match the Worker secret exactly."
elif [ -z "$MAILBOX" ]; then
  note "no mailbox address given, skipping signed delivery"
else
  ts="$(date +%s)"
  cat > "$BODY" <<EOF
{"message_id":"<readiness-$ts@verify.local>","sender":"readiness@verify.local","recipient":"$MAILBOX","subject":"Readiness check $ts","text":"Signed delivery probe.","received_at":"$(date -u +%Y-%m-%dT%H:%M:%SZ)","attachments":[]}
EOF
  sig="$( { printf '%s.' "$ts"; cat "$BODY"; } | openssl dgst -sha256 -hmac "$INBOUND_WEBHOOK_SECRET" -r | cut -d' ' -f1)"
  resp="$(curl -s -m 20 -X POST "$BASE/api/webhooks/inbound-email" \
    -H 'Content-Type: application/json' \
    -H "X-DailyMail-Timestamp: $ts" \
    -H "X-DailyMail-Signature: $sig" \
    --data-binary @"$BODY" -w '\n%{http_code}')"
  code="$(printf '%s' "$resp" | tail -1)"
  body="$(printf '%s' "$resp" | sed '$d')"
  case "$code:$body" in
    202:*stored*)  ok "signed POST -> 202 stored" ;;
    202:*ignored*) bad "signed POST -> 202 ignored" "The mailbox does not exist, is blocked or was deleted. Create it before sending mail." ;;
    401:*)         bad "signed POST -> 401" "Signature mismatch: INBOUND_WEBHOOK_SECRET differs from the Worker, or the clock is off by more than the tolerance." ;;
    503:*)         bad "signed POST -> 503" "Storage for attachments is unavailable (R2 not configured)." ;;
    *)             bad "signed POST -> $code" "$body" ;;
  esac

  if [ -n "${MAILBOX_PASSWORD:-}" ]; then
    token="$(curl -s -m 20 -X POST "$BASE/api/mailboxes/login" -H 'Content-Type: application/json' \
      -d "{\"email\":\"$MAILBOX\",\"password\":\"$MAILBOX_PASSWORD\"}" \
      | python3 -c 'import json,sys; print(json.load(sys.stdin).get("access_token",""))' 2>/dev/null)"
    if [ -z "$token" ]; then
      bad "mailbox login failed" "Check MAILBOX_PASSWORD."
    else
      count="$(curl -s -m 20 "$BASE/api/messages" -H "Authorization: Bearer $token" \
        | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d.get("items", d) if isinstance(d, dict) else d))' 2>/dev/null)"
      if [ -n "$count" ] && [ "$count" -ge 1 ] 2>/dev/null; then
        ok "inbox lists $count message(s) for $MAILBOX"
      else
        bad "inbox is empty or unreadable" "Delivery reported success but the message is not visible."
      fi
    fi
  else
    note "MAILBOX_PASSWORD not set, skipping inbox check"
  fi
fi

echo
if [ "$fail" -eq 0 ]; then
  echo "Result: $pass passed. Real inbound email should work — send one from an external account and press Atualizar in the site."
  exit 0
fi
echo "Result: $pass passed, $fail failed. Real inbound email will not work until the failures above are fixed."
exit 1
