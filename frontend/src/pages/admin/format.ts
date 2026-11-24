import { parseUtc } from '../../utils/datetime'

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  return parseUtc(value).toLocaleString('pt-PT', { dateStyle: 'short', timeStyle: 'short' })
}

export function formatDay(isoDay: string): string {
  return new Date(`${isoDay}T00:00:00Z`).toLocaleDateString('pt-PT', {
    day: 'numeric',
    month: 'short',
    timeZone: 'UTC',
  })
}

export function formatNumber(value: number): string {
  return value.toLocaleString('pt-PT')
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

export function formatDuration(totalSeconds: number): string {
  const days = Math.floor(totalSeconds / 86400)
  const hours = Math.floor((totalSeconds % 86400) / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  if (days > 0) return `${days}d ${hours}h`
  if (hours > 0) return `${hours}h ${minutes}min`
  return `${minutes}min`
}

export function percent(part: number, whole: number): string {
  return whole > 0 ? `${Math.round((part / whole) * 100)}%` : '0%'
}

export const ACTION_LABELS: Record<string, string> = {
  'admin.login': 'Início de sessão',
  'admin.create': 'Administrador criado',
  'admin.status': 'Estado de administrador alterado',
  'admin.password': 'Senha de administrador alterada',
  'mailbox.status': 'Estado da caixa alterado',
  'mailbox.delete': 'Caixa eliminada',
  'mailbox.password': 'Senha da caixa redefinida',
  'mailbox.sessions_revoked': 'Sessões da caixa terminadas',
  'mailbox.clear': 'Mensagens da caixa eliminadas',
  'message.delete': 'Mensagem eliminada',
  'attachment.delete': 'Anexo eliminado',
  'batch.password': 'Senha do lote redefinida',
  'maintenance.purge_messages': 'Limpeza de mensagens expiradas',
  'maintenance.purge_sessions': 'Limpeza de sessões expiradas',
}
