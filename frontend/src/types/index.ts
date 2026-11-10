export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
}

export interface MessageSummary {
  id: number
  sender: string
  recipient: string
  subject: string | null
  received_at: string
  expires_at: string | null
  is_read: boolean
}

export interface MessageDetail extends MessageSummary {
  text_body: string | null
  html_body_sanitized: string | null
}
