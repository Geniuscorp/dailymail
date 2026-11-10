export interface Mailbox {
  id: number
  email_address: string
  status: string
  created_at: string
  expires_at?: string
}

export interface Message {
  id: number
  sender: string
  recipient: string
  subject?: string
  received_at: string
  is_read: boolean
  attachment_count: number
}

export interface Attachment {
  id: number
  original_filename: string
  mime_type: string
  file_size: number
}
