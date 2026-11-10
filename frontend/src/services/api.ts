import axios from 'axios'
import { clearToken, getToken } from './session'
import type { MessageDetail, MessageSummary, TokenResponse } from '../types'

// An empty value means "same origin": nginx proxies /api to the backend.
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

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

client.interceptors.response.use(undefined, (error: unknown) => {
  if (axios.isAxiosError(error) && error.response?.status === 401 && getToken()) {
    clearToken()
    window.location.assign('/login')
  }
  return Promise.reject(error)
})

export async function login(email: string, password: string): Promise<TokenResponse> {
  const { data } = await client.post<TokenResponse>('/mailboxes/login', { email, password })
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
