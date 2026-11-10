import { useCallback, useEffect, useState, type FormEvent } from 'react'
import {
  adminLogin,
  deleteAdminMessage,
  getAdminDashboard,
  listAdminMailboxes,
  listAdminMessages,
  updateAdminMailboxStatus,
} from '../services/adminApi'
import { clearAdminToken, getAdminToken, setAdminToken } from '../services/session'
import type { AdminDashboard, AdminMailbox, AdminMessage } from '../types'

const PAGE_SIZE = 50

function formatDate(value: string): string {
  return new Date(value).toLocaleString('pt-PT', { dateStyle: 'short', timeStyle: 'short' })
}

function AdminLoginForm({ onSuccess }: { onSuccess: () => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const token = await adminLogin(username.trim(), password)
      setAdminToken(token.access_token)
      onSuccess()
    } catch {
      setError('Credenciais de administração inválidas.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="mx-auto max-w-sm space-y-6">
      <h1 className="text-2xl font-semibold">Administração</h1>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="admin-username" className="block text-sm font-medium text-gray-700">
            Utilizador
          </label>
          <input
            id="admin-username"
            autoComplete="username"
            required
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 focus:border-gray-900 focus:outline-none"
          />
        </div>
        <div>
          <label htmlFor="admin-password" className="block text-sm font-medium text-gray-700">
            Senha
          </label>
          <input
            id="admin-password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 focus:border-gray-900 focus:outline-none"
          />
        </div>
        {error && (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-md bg-gray-900 px-4 py-2 text-white hover:bg-gray-700 disabled:opacity-50"
        >
          {submitting ? 'A entrar…' : 'Entrar'}
        </button>
      </form>
    </section>
  )
}

function Stats({ dashboard }: { dashboard: AdminDashboard | null }) {
  if (!dashboard) return null

  const cards = [
    { label: 'Caixas ativas', value: `${dashboard.active_mailboxes} / ${dashboard.total_mailboxes}` },
    { label: 'Mensagens', value: dashboard.total_messages },
    { label: 'Anexos', value: dashboard.total_attachments },
    { label: 'Armazenamento', value: `${dashboard.storage_used_mb} MB` },
    { label: 'A expirar (7 dias)', value: dashboard.expiring_soon },
  ]

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
      {cards.map((card) => (
        <div key={card.label} className="rounded-md border border-gray-200 bg-white p-3">
          <p className="text-xs text-gray-500">{card.label}</p>
          <p className="mt-1 text-lg font-semibold text-gray-900">{card.value}</p>
        </div>
      ))}
    </div>
  )
}

export default function AdminPage() {
  const [authenticated, setAuthenticated] = useState(getAdminToken() !== null)
  const [dashboard, setDashboard] = useState<AdminDashboard | null>(null)
  const [mailboxes, setMailboxes] = useState<AdminMailbox[]>([])
  const [mailboxTotal, setMailboxTotal] = useState(0)
  const [messages, setMessages] = useState<AdminMessage[]>([])
  const [messageTotal, setMessageTotal] = useState(0)
  const [mailboxSearch, setMailboxSearch] = useState('')
  const [messageSearch, setMessageSearch] = useState('')
  const [tab, setTab] = useState<'mailboxes' | 'messages'>('mailboxes')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const loadDashboard = useCallback(async () => {
    try {
      setDashboard(await getAdminDashboard())
    } catch {
      setError('Não foi possível carregar as estatísticas.')
    }
  }, [])

  const loadMailboxes = useCallback(async (search: string) => {
    try {
      const page = await listAdminMailboxes({ search: search || undefined, limit: PAGE_SIZE })
      setMailboxes(page.items)
      setMailboxTotal(page.total)
    } catch {
      setError('Não foi possível carregar as caixas.')
    }
  }, [])

  const loadMessages = useCallback(async (search: string) => {
    try {
      const page = await listAdminMessages({ search: search || undefined, limit: PAGE_SIZE })
      setMessages(page.items)
      setMessageTotal(page.total)
    } catch {
      setError('Não foi possível carregar as mensagens.')
    }
  }, [])

  // `refreshAll` reads the current search terms, so it can be used from the
  // "Atualizar" button without making the load effect fire on every keystroke.
  const refreshAll = useCallback(async () => {
    setError(null)
    await Promise.all([loadDashboard(), loadMailboxes(mailboxSearch), loadMessages(messageSearch)])
  }, [loadDashboard, loadMailboxes, loadMessages, mailboxSearch, messageSearch])

  useEffect(() => {
    if (!authenticated) return
    setError(null)
    void Promise.all([loadDashboard(), loadMailboxes(''), loadMessages('')])
  }, [authenticated, loadDashboard, loadMailboxes, loadMessages])

  async function toggleMailbox(mailbox: AdminMailbox) {
    setError(null)
    setBusy(true)
    try {
      await updateAdminMailboxStatus(mailbox.id, mailbox.status === 'blocked' ? 'active' : 'blocked')
      await Promise.all([loadDashboard(), loadMailboxes(mailboxSearch)])
    } catch {
      setError('Não foi possível alterar o estado da caixa.')
    } finally {
      setBusy(false)
    }
  }

  async function removeMessage(message: AdminMessage) {
    if (!window.confirm('Eliminar esta mensagem e os seus anexos?')) return
    setError(null)
    setBusy(true)
    try {
      await deleteAdminMessage(message.id)
      await Promise.all([loadDashboard(), loadMessages(messageSearch)])
    } catch {
      setError('Não foi possível eliminar a mensagem.')
    } finally {
      setBusy(false)
    }
  }

  function logout() {
    clearAdminToken()
    setAuthenticated(false)
    setDashboard(null)
    setMailboxes([])
    setMessages([])
  }

  if (!authenticated) {
    return <AdminLoginForm onSuccess={() => setAuthenticated(true)} />
  }

  return (
    <section className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Administração</h1>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => void refreshAll()}
            className="rounded-md px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100"
          >
            Atualizar
          </button>
          <button
            type="button"
            onClick={logout}
            className="rounded-md px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100"
          >
            Sair
          </button>
        </div>
      </div>

      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}

      <Stats dashboard={dashboard} />

      <div className="flex gap-2">
        {(['mailboxes', 'messages'] as const).map((value) => (
          <button
            key={value}
            type="button"
            onClick={() => setTab(value)}
            className={`rounded-md px-3 py-1.5 text-sm ${
              tab === value ? 'bg-gray-900 text-white' : 'text-gray-600 hover:bg-gray-100'
            }`}
          >
            {value === 'mailboxes' ? 'Caixas' : 'Mensagens'}
          </button>
        ))}
      </div>

      {tab === 'mailboxes' && (
        <div className="space-y-3">
          <form
            onSubmit={(event) => {
              event.preventDefault()
              void loadMailboxes(mailboxSearch)
            }}
            className="flex gap-2"
          >
            <input
              value={mailboxSearch}
              onChange={(event) => setMailboxSearch(event.target.value)}
              placeholder="Procurar por endereço"
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-gray-900 focus:outline-none"
            />
            <button
              type="submit"
              className="rounded-md border border-gray-300 px-3 py-2 text-sm hover:bg-gray-50"
            >
              Procurar
            </button>
          </form>

          <p className="text-xs text-gray-500">{mailboxTotal} caixa(s)</p>

          <ul className="divide-y divide-gray-200 rounded-md border border-gray-200 bg-white">
            {mailboxes.map((mailbox) => (
              <li key={mailbox.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
                <div className="min-w-0">
                  <p className="truncate text-sm text-gray-900">{mailbox.email_address}</p>
                  <p className="text-xs text-gray-500">
                    {mailbox.status} · {mailbox.message_count} mensagem(ns) · criada em{' '}
                    {formatDate(mailbox.created_at)}
                  </p>
                </div>
                <button
                  type="button"
                  disabled={busy || mailbox.status === 'deleted'}
                  onClick={() => void toggleMailbox(mailbox)}
                  className="rounded-md border border-gray-300 px-3 py-1 text-sm hover:bg-gray-50 disabled:opacity-50"
                >
                  {mailbox.status === 'deleted'
                    ? 'Eliminada'
                    : mailbox.status === 'blocked'
                      ? 'Ativar'
                      : 'Bloquear'}
                </button>
              </li>
            ))}
          </ul>
          {mailboxes.length === 0 && <p className="text-sm text-gray-500">Sem resultados.</p>}
        </div>
      )}

      {tab === 'messages' && (
        <div className="space-y-3">
          <form
            onSubmit={(event) => {
              event.preventDefault()
              void loadMessages(messageSearch)
            }}
            className="flex gap-2"
          >
            <input
              value={messageSearch}
              onChange={(event) => setMessageSearch(event.target.value)}
              placeholder="Procurar por remetente, destinatário ou assunto"
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-gray-900 focus:outline-none"
            />
            <button
              type="submit"
              className="rounded-md border border-gray-300 px-3 py-2 text-sm hover:bg-gray-50"
            >
              Procurar
            </button>
          </form>

          <p className="text-xs text-gray-500">{messageTotal} mensagem(ns)</p>

          <ul className="divide-y divide-gray-200 rounded-md border border-gray-200 bg-white">
            {messages.map((message) => (
              <li key={message.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
                <div className="min-w-0">
                  <p className="truncate text-sm text-gray-900">
                    {message.subject || '(sem assunto)'}
                  </p>
                  <p className="truncate text-xs text-gray-500">
                    {message.sender} → {message.recipient} · {formatDate(message.received_at)} ·{' '}
                    {message.attachment_count} anexo(s)
                  </p>
                </div>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void removeMessage(message)}
                  className="rounded-md border border-red-300 px-3 py-1 text-sm text-red-700 hover:bg-red-50 disabled:opacity-50"
                >
                  Eliminar
                </button>
              </li>
            ))}
          </ul>
          {messages.length === 0 && <p className="text-sm text-gray-500">Sem resultados.</p>}
        </div>
      )}
    </section>
  )
}
