import axios from 'axios'
import { API_BASE_URL } from './api'
import { clearAdminToken, getAdminToken } from './session'
import type {
  AdminAttachmentPage,
  AdminAuditPage,
  AdminBatchPage,
  AdminDashboard,
  AdminMailbox,
  AdminMailboxDetail,
  AdminMailboxPage,
  AdminMessageDetail,
  AdminMessagePage,
  AdminOverview,
  AdminSystem,
  AdminUserInfo,
  MailboxStatus,
  TokenResponse,
} from '../types'

const admin = axios.create({
  baseURL: `${API_BASE_URL}/api/admin`,
  headers: { 'Content-Type': 'application/json' },
})

admin.interceptors.request.use((config) => {
  const token = getAdminToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

admin.interceptors.response.use(undefined, (error: unknown) => {
  if (axios.isAxiosError(error) && error.response?.status === 401 && getAdminToken()) {
    clearAdminToken()
    window.location.assign('/admin')
  }
  return Promise.reject(error)
})

export async function adminLogin(username: string, password: string): Promise<TokenResponse> {
  const { data } = await admin.post<TokenResponse>('/login', { username, password })
  return data
}

export async function getAdminDashboard(): Promise<AdminDashboard> {
  const { data } = await admin.get<AdminDashboard>('/dashboard')
  return data
}

export async function listAdminMailboxes(params: {
  search?: string
  status?: MailboxStatus
  limit?: number
  offset?: number
}): Promise<AdminMailboxPage> {
  const { data } = await admin.get<AdminMailboxPage>('/mailboxes', { params })
  return data
}

export async function updateAdminMailboxStatus(
  id: number,
  status: MailboxStatus,
): Promise<AdminMailbox> {
  const { data } = await admin.patch<AdminMailbox>(`/mailboxes/${id}`, { status })
  return data
}

export async function listAdminMessages(params: {
  search?: string
  mailbox_id?: number
  unread?: boolean
  has_attachments?: boolean
  limit?: number
  offset?: number
}): Promise<AdminMessagePage> {
  const { data } = await admin.get<AdminMessagePage>('/messages', { params })
  return data
}

export async function deleteAdminMessage(id: number): Promise<void> {
  await admin.delete(`/messages/${id}`)
}

export async function getAdminOverview(days: number): Promise<AdminOverview> {
  const { data } = await admin.get<AdminOverview>('/overview', { params: { days } })
  return data
}

export async function getAdminSystem(): Promise<AdminSystem> {
  const { data } = await admin.get<AdminSystem>('/system')
  return data
}

export async function listAdminAudit(params: {
  action?: string
  limit?: number
  offset?: number
}): Promise<AdminAuditPage> {
  const { data } = await admin.get<AdminAuditPage>('/audit-logs', { params })
  return data
}

export async function getAdminMailbox(id: number): Promise<AdminMailboxDetail> {
  const { data } = await admin.get<AdminMailboxDetail>(`/mailboxes/${id}`)
  return data
}

export async function resetAdminMailboxPassword(id: number, newPassword: string): Promise<void> {
  await admin.post(`/mailboxes/${id}/password`, { new_password: newPassword })
}

export async function revokeAdminMailboxSessions(id: number): Promise<number> {
  const { data } = await admin.delete<{ affected: number }>(`/mailboxes/${id}/sessions`)
  return data.affected
}

export async function clearAdminMailboxMessages(id: number): Promise<number> {
  const { data } = await admin.delete<{ affected: number }>(`/mailboxes/${id}/messages`)
  return data.affected
}

export async function deleteAdminMailbox(id: number): Promise<void> {
  await admin.delete(`/mailboxes/${id}`)
}

export async function bulkAdminMailboxStatus(ids: number[], status: MailboxStatus): Promise<number> {
  const { data } = await admin.post<{ affected: number }>('/mailboxes/bulk-status', { ids, status })
  return data.affected
}

export async function exportAdminMailboxes(params: { search?: string; status?: MailboxStatus }): Promise<Blob> {
  const { data } = await admin.get<Blob>('/mailboxes/export', { params, responseType: 'blob' })
  return data
}

export async function getAdminMessage(id: number): Promise<AdminMessageDetail> {
  const { data } = await admin.get<AdminMessageDetail>(`/messages/${id}`)
  return data
}

export async function listAdminAttachments(params: {
  search?: string
  message_id?: number
  limit?: number
  offset?: number
}): Promise<AdminAttachmentPage> {
  const { data } = await admin.get<AdminAttachmentPage>('/attachments', { params })
  return data
}

export async function deleteAdminAttachment(id: number): Promise<void> {
  await admin.delete(`/attachments/${id}`)
}

export async function downloadAdminAttachment(id: number): Promise<Blob> {
  const { data } = await admin.get<Blob>(`/attachments/${id}/download`, { responseType: 'blob' })
  return data
}

export async function listAdminBatches(params: { limit?: number; offset?: number }): Promise<AdminBatchPage> {
  const { data } = await admin.get<AdminBatchPage>('/batches', { params })
  return data
}

export async function resetAdminBatchPassword(id: number, newPassword: string): Promise<void> {
  await admin.patch(`/batches/${id}/password`, { new_password: newPassword })
}

export async function getAdminMe(): Promise<AdminUserInfo> {
  const { data } = await admin.get<AdminUserInfo>('/me')
  return data
}

export async function listAdminUsers(): Promise<AdminUserInfo[]> {
  const { data } = await admin.get<AdminUserInfo[]>('/users')
  return data
}

export async function createAdminUser(username: string, password: string): Promise<AdminUserInfo> {
  const { data } = await admin.post<AdminUserInfo>('/users', { username, password })
  return data
}

export async function setAdminUserStatus(id: number, status: 'active' | 'inactive'): Promise<AdminUserInfo> {
  const { data } = await admin.patch<AdminUserInfo>(`/users/${id}`, { status })
  return data
}

export async function changeAdminPassword(currentPassword: string, newPassword: string): Promise<void> {
  await admin.post('/me/password', { current_password: currentPassword, new_password: newPassword })
}

export async function purgeExpiredMessages(): Promise<number> {
  const { data } = await admin.post<{ affected: number }>('/maintenance/purge-expired')
  return data.affected
}

export async function purgeExpiredSessions(): Promise<number> {
  const { data } = await admin.post<{ affected: number }>('/maintenance/purge-sessions')
  return data.affected
}

export function adminErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const status = error.response?.status
    const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail
    if (status === 429) return 'Demasiados pedidos. Tenta novamente daqui a pouco.'
    if (status === 503) return 'Serviço indisponível (armazenamento de anexos).'
    if (status === 422) return 'Dados inválidos. Verifica os campos.'
    if (typeof detail === 'string' && status !== undefined && status < 500) return detail
    if (!error.response) return 'Sem ligação ao servidor.'
  }
  return fallback
}
