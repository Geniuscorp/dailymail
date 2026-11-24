export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
}

export interface MailboxInfo {
  id: number
  email_address: string
  status: string
  created_at: string
  expires_at: string | null
  batch_id: number | null
}

export interface MessageSummary {
  id: number
  sender: string
  recipient: string
  subject: string | null
  received_at: string
  expires_at: string | null
  is_read: boolean
  attachment_count: number
}

export interface AttachmentSummary {
  id: number
  original_filename: string
  mime_type: string
  file_size: number
  created_at: string
}

export interface MessageDetail extends MessageSummary {
  text_body: string | null
  html_body_sanitized: string | null
  attachments: AttachmentSummary[]
}

export interface AdminDashboard {
  total_mailboxes: number
  active_mailboxes: number
  total_messages: number
  total_attachments: number
  storage_used_mb: number
  expiring_soon: number
}

export type MailboxStatus = 'active' | 'blocked' | 'deleted'

export interface AdminMailbox {
  id: number
  email_address: string
  status: MailboxStatus
  batch_id: number | null
  created_at: string
  message_count: number
}

export interface AdminMailboxPage {
  total: number
  limit: number
  offset: number
  items: AdminMailbox[]
}

export interface AdminAttachment {
  id: number
  message_id: number
  original_filename: string
  mime_type: string
  file_size: number
  created_at: string
  mailbox_id: number
  mailbox_email: string
  sender: string
  subject: string | null
  received_at: string
}

export interface AdminAttachmentPage {
  total: number
  limit: number
  offset: number
  items: AdminAttachment[]
}

export interface AdminMessage {
  id: number
  mailbox_id: number
  recipient: string
  sender: string
  subject: string | null
  received_at: string
  expires_at: string | null
  is_read: boolean
  attachment_count: number
}

export interface AdminMessagePage {
  total: number
  limit: number
  offset: number
  items: AdminMessage[]
}

export interface AdminBatch {
  id: number
  quantity: number
  generation_type: string
  created_at: string
  mailbox_count: number
}

export interface AdminBatchPage {
  total: number
  limit: number
  offset: number
  items: AdminBatch[]
}

export interface AdminMailboxDetail extends AdminMailbox {
  unread_count: number
  attachment_count: number
  storage_bytes: number
  live_sessions: number
  last_message_at: string | null
  recent_messages: AdminMessage[]
}

export interface AdminMessageDetail extends AdminMessage {
  text_body: string | null
  attachments: AdminAttachment[]
}

export interface AdminAuditEntry {
  id: number
  admin_username: string | null
  action: string
  target_type: string
  target_id: string | null
  created_at: string
}

export interface AdminAuditPage {
  total: number
  limit: number
  offset: number
  items: AdminAuditEntry[]
}

export interface AdminUserInfo {
  id: number
  username: string
  status: 'active' | 'inactive'
  created_at: string | null
}

export interface DailyPoint {
  date: string
  messages: number
  mailboxes: number
  attachments: number
  attachment_bytes: number
}

export interface LabelCount {
  label: string
  count: number
}

export interface AdminOverview {
  days: number
  mailboxes: { total: number; active: number; blocked: number; deleted: number }
  messages: {
    total: number
    unread: number
    last_24h: number
    last_7d: number
    expiring_soon: number
    expired_pending: number
  }
  attachments: { total: number; bytes: number; largest_bytes: number; average_bytes: number }
  activity: {
    new_mailboxes_24h: number
    new_mailboxes_7d: number
    active_mailboxes_24h: number
    batches: number
    live_sessions: number
    admins: number
  }
  series: DailyPoint[]
  top_senders: LabelCount[]
  top_sender_domains: LabelCount[]
  busiest_mailboxes: { mailbox_id: number; email_address: string; count: number }[]
  attachment_types: { mime_type: string; count: number; bytes: number }[]
}

export interface AdminSystem {
  app_name: string
  version: string
  environment: string
  debug: boolean
  python: string
  uptime_seconds: number
  started_at: string
  domain: string
  database: { dialect: string; size_bytes: number | null }
  inbound: { provider: string; webhook_secret_set: boolean; max_payload_mb: number }
  storage: {
    configured: boolean
    bucket: string | null
    max_attachment_mb: number
    max_attachments_per_message: number
  }
  retention: { days: number; sweep_enabled: boolean; sweep_interval_hours: number }
  protection: {
    rate_limit_enabled: boolean
    create_per_minute: number
    login_per_minute: number
    webhook_per_minute: number
    creation_secret_required: boolean
    mailbox_session_days: number
    admin_token_minutes: number
    limiter: {
      blocked_total: number
      recent_clients: number
      top_blocked: { scope: string; client: string; count: number; last_blocked_at: string }[]
    }
  }
}
