import PostalMime from "postal-mime";

const MAX_RAW_BYTES = 25 * 1024 * 1024;

function toHex(buffer) {
  return [...new Uint8Array(buffer)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function toBase64(bytes) {
  const view = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < view.length; i += chunk) {
    binary += String.fromCharCode(...view.subarray(i, i + chunk));
  }
  return btoa(binary);
}

async function sign(secret, timestamp, body) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const data = new TextEncoder().encode(`${timestamp}.${body}`);
  return toHex(await crypto.subtle.sign("HMAC", key, data));
}

function toPayload(email, message) {
  return {
    message_id: email.messageId || `<${crypto.randomUUID()}@dailymail.worker>`,
    sender: message.from,
    recipient: message.to,
    subject: email.subject || null,
    text: email.text || null,
    html: email.html || null,
    received_at: new Date().toISOString(),
    attachments: (email.attachments || [])
      .filter((attachment) => attachment.content)
      .map((attachment) => ({
        filename: attachment.filename || null,
        content_type: attachment.mimeType || null,
        content_base64: toBase64(attachment.content),
      })),
  };
}

export default {
  async email(message, env) {
    if (message.rawSize > MAX_RAW_BYTES) {
      message.setReject("Message too large");
      return;
    }

    const raw = await new Response(message.raw).arrayBuffer();
    const email = await new PostalMime().parse(raw);

    const body = JSON.stringify(toPayload(email, message));
    const timestamp = Math.floor(Date.now() / 1000).toString();
    const signature = await sign(env.INBOUND_WEBHOOK_SECRET, timestamp, body);

    const response = await fetch(`${env.BACKEND_URL}/api/webhooks/inbound-email`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-DailyMail-Timestamp": timestamp,
        "X-DailyMail-Signature": signature,
      },
      body,
    });

    if (response.status >= 500) {
      throw new Error(`Backend unavailable (${response.status}); message will be retried by sender`);
    }
    if (response.status >= 400) {
      message.setReject(`Delivery rejected by backend (${response.status})`);
    }
  },
};
