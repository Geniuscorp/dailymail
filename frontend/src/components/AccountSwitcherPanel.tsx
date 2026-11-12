import { useEffect, useState, type FormEvent } from 'react'
import { createMailbox, getCurrentMailbox, login, MAIL_DOMAIN } from '../services/api'
import {
  forgetAccount,
  getToken,
  listAccounts,
  rememberAccount,
  setToken,
  type RememberedAccount,
} from '../services/session'

const LOCAL_PART_PATTERN = /^[a-z0-9][a-z0-9._-]{0,63}$/

type Mode = 'idle' | 'create' | 'login'

// Switching accounts reloads the page: the inbox's SSE connection and
// in-flight requests are all scoped to whichever mailbox was authenticated
// when they started, so a clean reload is simpler and more robust than
// trying to re-point everything live.
function switchToAccount(email: string, token: string) {
  rememberAccount(email, token)
  setToken(token)
  window.location.assign('/inbox')
}

function FieldError({ message }: { message: string }) {
  return (
    <p role="alert" className="text-xs text-red-600">
      {message}
    </p>
  )
}

function QuickLoginForm({ onCancel }: { onCancel: () => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const normalized = email.trim().toLowerCase()
      const token = await login(normalized, password)
      switchToAccount(normalized, token.access_token)
    } catch {
      setError('Endereço ou senha incorretos.')
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2 rounded-xl border border-gray-200 bg-gray-50 p-3">
      <input
        type="email"
        autoComplete="username"
        required
        placeholder="endereço@dominio"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        className="w-full rounded-lg border border-gray-300 bg-white px-2.5 py-1.5 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
      />
      <input
        type="password"
        autoComplete="current-password"
        required
        placeholder="Senha"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        className="w-full rounded-lg border border-gray-300 bg-white px-2.5 py-1.5 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
      />
      {error && <FieldError message={error} />}
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={submitting}
          className="flex-1 rounded-lg bg-indigo-600 px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {submitting ? 'A entrar…' : 'Entrar'}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg px-2.5 py-1.5 text-xs font-medium text-gray-500 hover:bg-gray-100"
        >
          Cancelar
        </button>
      </div>
    </form>
  )
}

function QuickCreateForm({ onCancel }: { onCancel: () => void }) {
  const [localPart, setLocalPart] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)

    const normalized = localPart.trim().toLowerCase()
    if (!LOCAL_PART_PATTERN.test(normalized)) {
      setError('Usa só letras minúsculas, números, pontos, hífens ou underscores.')
      return
    }
    if (password.length < 8) {
      setError('Mínimo de 8 caracteres.')
      return
    }

    const emailAddress = `${normalized}@${MAIL_DOMAIN}`
    setSubmitting(true)
    try {
      await createMailbox(emailAddress, password)
      const token = await login(emailAddress, password)
      switchToAccount(emailAddress, token.access_token)
    } catch (err) {
      const status = (err as { response?: { status?: number } })?.response?.status
      setError(status === 409 ? 'Esse endereço já existe.' : 'Não foi possível criar a conta.')
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2 rounded-xl border border-gray-200 bg-gray-50 p-3">
      <div className="flex items-center overflow-hidden rounded-lg border border-gray-300 bg-white focus-within:border-indigo-500 focus-within:ring-2 focus-within:ring-indigo-100">
        <input
          autoComplete="off"
          required
          placeholder="novo-endereço"
          value={localPart}
          onChange={(e) => setLocalPart(e.target.value)}
          className="w-full px-2.5 py-1.5 text-sm outline-none"
        />
        <span className="shrink-0 pr-2.5 text-xs text-gray-400">@{MAIL_DOMAIN}</span>
      </div>
      <input
        type="password"
        autoComplete="new-password"
        required
        minLength={8}
        placeholder="Senha"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        className="w-full rounded-lg border border-gray-300 bg-white px-2.5 py-1.5 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
      />
      {error && <FieldError message={error} />}
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={submitting}
          className="flex-1 rounded-lg bg-indigo-600 px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {submitting ? 'A criar…' : 'Criar'}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg px-2.5 py-1.5 text-xs font-medium text-gray-500 hover:bg-gray-100"
        >
          Cancelar
        </button>
      </div>
    </form>
  )
}

function OtherAccountsList({ accounts, onForget }: { accounts: RememberedAccount[]; onForget: (email: string) => void }) {
  if (accounts.length === 0) return null

  return (
    <div className="space-y-1">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-400">Outras contas</h3>
      <ul className="space-y-1">
        {accounts.map((account) => (
          <li
            key={account.email}
            className="group flex items-center gap-1 rounded-lg border border-gray-200 pl-1"
          >
            <button
              type="button"
              onClick={() => switchToAccount(account.email, account.token)}
              className="min-w-0 flex-1 truncate rounded-lg px-2 py-1.5 text-left text-sm text-gray-700 transition-colors hover:bg-gray-50"
              title={account.email}
            >
              {account.email}
            </button>
            <button
              type="button"
              onClick={() => onForget(account.email)}
              aria-label={`Esquecer ${account.email}`}
              title="Esquecer esta conta"
              className="shrink-0 rounded-lg px-2 py-1.5 text-xs text-gray-400 opacity-0 transition-opacity hover:bg-red-50 hover:text-red-600 group-hover:opacity-100"
            >
              ✕
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function AccountSwitcherPanel() {
  const [email, setEmail] = useState<string | null>(null)
  const [mode, setMode] = useState<Mode>('idle')
  const [accounts, setAccounts] = useState<RememberedAccount[]>(() => listAccounts())

  useEffect(() => {
    getCurrentMailbox()
      .then((mailbox) => {
        setEmail(mailbox.email_address)
        // The account this tab is actually using should always be
        // remembered too, even if it got here via a direct link or an
        // older session predating this list.
        const token = getToken()
        if (token) rememberAccount(mailbox.email_address, token)
        setAccounts(listAccounts())
      })
      .catch(() => undefined)
  }, [])

  function handleForget(forgottenEmail: string) {
    forgetAccount(forgottenEmail)
    setAccounts(listAccounts())
  }

  const otherAccounts = accounts.filter((account) => account.email !== email)

  return (
    <div className="space-y-4 p-5">
      <div>
        <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-400">Conta atual</h2>
        <p className="mt-1.5 truncate text-sm font-medium text-gray-900" title={email ?? undefined}>
          {email ?? '…'}
        </p>
      </div>

      <OtherAccountsList accounts={otherAccounts} onForget={handleForget} />

      {mode === 'idle' && (
        <div className="space-y-1.5">
          <button
            type="button"
            onClick={() => setMode('create')}
            className="w-full rounded-lg border border-gray-200 px-3 py-1.5 text-left text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
          >
            + Criar outra conta
          </button>
          <button
            type="button"
            onClick={() => setMode('login')}
            className="w-full rounded-lg border border-gray-200 px-3 py-1.5 text-left text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
          >
            Entrar noutra conta
          </button>
        </div>
      )}
      {mode === 'create' && <QuickCreateForm onCancel={() => setMode('idle')} />}
      {mode === 'login' && <QuickLoginForm onCancel={() => setMode('idle')} />}
    </div>
  )
}
