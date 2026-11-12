import axios from 'axios'
import { clearToken, forgetAccountByToken, getToken } from './session'
import type { MailboxInfo, MessageDetail, MessageSummary, TokenResponse } from '../types'

// An empty value means "same origin": nginx proxies /api to the backend.
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
export const MAIL_DOMAIN = import.meta.env.VITE_MAIL_DOMAIN ?? 'kupay.site'

const client = axios.create({
  baseURL: `${API_BASE_URL}/api`,
  headers: { 'Content-Type': 'application/json' },
})

client.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// These two endpoints work without a valid session (that's the point of
// them), so a 401 from either one means "wrong password" / "bad request",
// never "the current session is invalid" - even though the request
// interceptor above attaches today's token to every request regardless of
// whether the endpoint needs it. Without this exclusion, typing the wrong
// password for a *different* account in the switcher's quick-login form
// would log the user out of the account they were already in.
const UNAUTHENTICATED_PATHS = new Set(['/mailboxes/login', '/mailboxes'])

client.interceptors.response.use(undefined, (error: unknown) => {
  if (
    axios.isAxiosError(error) &&
    error.response?.status === 401 &&
    !UNAUTHENTICATED_PATHS.has(error.config?.url ?? '')
  ) {
    const token = getToken()
    if (token) {
      // The session was rejected - it expired, was revoked elsewhere, or the
      // password changed. It would never succeed again, so drop it from the
      // switcher list instead of leaving a "switch" button that just fails.
      forgetAccountByToken(token)
      clearToken()
      window.location.assign('/login')
    }
  }
  return Promise.reject(error)
})

export async function login(email: string, password: string): Promise<TokenResponse> {
  const { data } = await client.post<TokenResponse>('/mailboxes/login', { email, password })
  return data
}

export async function logout(): Promise<void> {
  // Best-effort: the session is cleared client-side regardless of whether
  // the server call succeeds (e.g. the token already expired).
  try {
    await client.post('/mailboxes/logout')
  } catch {
    // Ignored: the caller clears the local token either way.
  }
}

export async function createMailbox(emailAddress: string, password: string): Promise<void> {
  await client.post('/mailboxes', { email_address: emailAddress, password })
}

export async function updatePassword(currentPassword: string, newPassword: string): Promise<void> {
  await client.patch('/mailboxes/me/password', {
    current_password: currentPassword,
    new_password: newPassword,
  })
}

export async function deleteAccount(): Promise<void> {
  await client.delete('/mailboxes/me')
}

export async function getCurrentMailbox(): Promise<MailboxInfo> {
  const { data } = await client.get<MailboxInfo>('/mailboxes/me')
  return data
}

export async function listMessages(limit = 50): Promise<MessageSummary[]> {
  const { data } = await client.get<MessageSummary[]>('/messages', { params: { limit } })
  return data
}

export async function getMessage(id: number): Promise<MessageDetail> {
  const { data } = await client.get<MessageDetail>(`/messages/${id}`)
  return data
}

export async function setMessageRead(id: number, isRead: boolean): Promise<MessageSummary> {
  const { data } = await client.patch<MessageSummary>(`/messages/${id}/read`, { is_read: isRead })
  return data
}

export async function deleteMessage(id: number): Promise<void> {
  await client.delete(`/messages/${id}`)
}

export async function fetchAttachment(id: number): Promise<Blob> {
  const { data } = await client.get<Blob>(`/attachments/${id}/download`, { responseType: 'blob' })
  return data
}
