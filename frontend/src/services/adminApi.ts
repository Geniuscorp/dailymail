import axios from 'axios'
import { API_BASE_URL } from './api'
import { clearAdminToken, getAdminToken } from './session'
import type {
  AdminDashboard,
  AdminMailbox,
  AdminMailboxPage,
  AdminMessagePage,
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
  limit?: number
  offset?: number
}): Promise<AdminMessagePage> {
  const { data } = await admin.get<AdminMessagePage>('/messages', { params })
  return data
}

export async function deleteAdminMessage(id: number): Promise<void> {
  await admin.delete(`/messages/${id}`)
}
