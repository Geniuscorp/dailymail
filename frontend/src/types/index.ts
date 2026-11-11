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
