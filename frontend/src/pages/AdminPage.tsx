import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import AttachmentsTab from './admin/AttachmentsTab'
import AuditTab from './admin/AuditTab'
import BatchesTab from './admin/BatchesTab'
import MailboxesTab from './admin/MailboxesTab'
import MessagesTab from './admin/MessagesTab'
import OverviewTab from './admin/OverviewTab'
import SystemTab from './admin/SystemTab'
import { inputClass, Notice, primaryButtonClass } from './admin/ui'
import { adminErrorMessage, adminLogin } from '../services/adminApi'
import { clearAdminToken, getAdminToken, setAdminToken } from '../services/session'

type TabId = 'overview' | 'mailboxes' | 'messages' | 'attachments' | 'batches' | 'audit' | 'system'

const TABS: { id: TabId; label: string }[] = [
  { id: 'overview', label: 'Visão geral' },
  { id: 'mailboxes', label: 'Caixas' },
  { id: 'messages', label: 'Mensagens' },
  { id: 'attachments', label: 'Anexos' },
  { id: 'batches', label: 'Lotes' },
  { id: 'audit', label: 'Auditoria' },
  { id: 'system', label: 'Sistema' },
]

function tabFromHash(): TabId {
  const hash = window.location.hash.replace('#', '')
  return TABS.some((tab) => tab.id === hash) ? (hash as TabId) : 'overview'
}

function Logo() {
  return (
    <span className="flex items-center gap-2">
      <svg viewBox="0 0 24 24" fill="none" className="h-6 w-6" aria-hidden="true">
        <rect x="3" y="5" width="18" height="14" rx="3" className="fill-indigo-600" />
        <path d="M5 8l6.3 4.2a2 2 0 0 0 2.2 0L20 8" stroke="white" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span className="text-lg font-semibold tracking-tight text-gray-900">DailyMail</span>
      <span className="hidden rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-700 sm:inline">Administração</span>
    </span>
  )
}

function loginErrorMessage(error: unknown): string {
  const text = adminErrorMessage(error, 'Não foi possível entrar. Tenta novamente.')
  if (text === 'Invalid username or password') return 'Credenciais de administração inválidas.'
  if (text === 'Admin access is not configured') {
    return 'O acesso de administração não está configurado neste servidor (falta ADMIN_PASSWORD_HASH).'
  }
  return text
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
    } catch (err) {
      setError(loginErrorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <section className="w-full max-w-sm space-y-6 rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
        <Logo />
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
              className={`${inputClass} mt-1`}
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
              className={`${inputClass} mt-1`}
            />
          </div>
          {error && <Notice kind="error">{error}</Notice>}
          <button type="submit" disabled={submitting} className={`${primaryButtonClass} w-full py-2`}>
            {submitting ? 'A entrar…' : 'Entrar'}
          </button>
        </form>
        <Link to="/" className="block text-center text-xs text-gray-500 hover:text-gray-700">
          Voltar ao site
        </Link>
      </section>
    </div>
  )
}

export default function AdminPage() {
  const [authenticated, setAuthenticated] = useState(getAdminToken() !== null)
  const [tab, setTab] = useState<TabId>(tabFromHash)
  const [focusMailboxId, setFocusMailboxId] = useState<number | null>(null)
  const [messagesMailboxId, setMessagesMailboxId] = useState<number | null>(null)

  useEffect(() => {
    const onHashChange = () => setTab(tabFromHash())
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  const goTo = useCallback((next: TabId) => {
    setTab(next)
    window.history.replaceState(null, '', `#${next}`)
  }, [])

  const openMailbox = useCallback(
    (id: number) => {
      setFocusMailboxId(id)
      goTo('mailboxes')
    },
    [goTo],
  )

  const viewMessages = useCallback(
    (id: number) => {
      setMessagesMailboxId(id)
      goTo('messages')
    },
    [goTo],
  )

  const handleFocusHandled = useCallback(() => setFocusMailboxId(null), [])

  function logout() {
    clearAdminToken()
    setAuthenticated(false)
  }

  if (!authenticated) {
    return <AdminLoginForm onSuccess={() => setAuthenticated(true)} />
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="sticky top-0 z-30 border-b border-gray-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
          <Logo />
          <div className="flex items-center gap-1">
            <Link to="/" className="whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium text-gray-600 hover:bg-gray-100 hover:text-gray-900">
              Voltar ao site
            </Link>
            <button
              type="button"
              onClick={logout}
              className="rounded-lg px-3 py-1.5 text-sm font-medium text-gray-600 hover:bg-gray-100 hover:text-gray-900"
            >
              Sair
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto flex max-w-7xl gap-6 px-4 py-6">
        <nav aria-label="Secções" className="hidden w-48 shrink-0 lg:block">
          <ul className="sticky top-20 space-y-1">
            {TABS.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  aria-current={tab === item.id ? 'page' : undefined}
                  onClick={() => goTo(item.id)}
                  className={`w-full rounded-lg px-3 py-2 text-left text-sm font-medium transition-colors ${
                    tab === item.id ? 'bg-indigo-50 text-indigo-700' : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                  }`}
                >
                  {item.label}
                </button>
              </li>
            ))}
          </ul>
        </nav>

        <main className="min-w-0 flex-1 space-y-5">
          <nav aria-label="Secções" className="-mx-1 flex gap-1 overflow-x-auto pb-1 lg:hidden">
            {TABS.map((item) => (
              <button
                key={item.id}
                type="button"
                aria-current={tab === item.id ? 'page' : undefined}
                onClick={() => goTo(item.id)}
                className={`shrink-0 rounded-lg px-3 py-1.5 text-sm font-medium ${
                  tab === item.id ? 'bg-indigo-600 text-white' : 'text-gray-600 hover:bg-gray-100'
                }`}
              >
                {item.label}
              </button>
            ))}
          </nav>

          <h1 className="text-2xl font-bold tracking-tight text-gray-900">
            {TABS.find((item) => item.id === tab)?.label}
          </h1>

          {tab === 'overview' && <OverviewTab onOpenMailbox={openMailbox} />}
          {tab === 'mailboxes' && (
            <MailboxesTab focusId={focusMailboxId} onFocusHandled={handleFocusHandled} onViewMessages={viewMessages} />
          )}
          {tab === 'messages' && (
            <MessagesTab
              mailboxId={messagesMailboxId}
              onClearMailbox={() => setMessagesMailboxId(null)}
              onOpenMailbox={openMailbox}
            />
          )}
          {tab === 'attachments' && <AttachmentsTab />}
          {tab === 'batches' && <BatchesTab />}
          {tab === 'audit' && <AuditTab />}
          {tab === 'system' && <SystemTab />}
        </main>
      </div>
    </div>
  )
}
