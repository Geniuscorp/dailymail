import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { createMailbox, login, MAIL_DOMAIN } from '../services/api'
import { setToken } from '../services/session'

const LOCAL_PART_PATTERN = /^[a-z0-9][a-z0-9._-]{0,63}$/

export default function CreateMailboxPage() {
  const navigate = useNavigate()
  const [localPart, setLocalPart] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)

    const normalized = localPart.trim().toLowerCase()
    if (!LOCAL_PART_PATTERN.test(normalized)) {
      setError('Usa apenas letras minúsculas, números, pontos, hífens ou underscores.')
      return
    }
    if (password.length < 8) {
      setError('A senha precisa de pelo menos 8 caracteres.')
      return
    }
    if (password !== confirmPassword) {
      setError('As senhas não coincidem.')
      return
    }

    const emailAddress = `${normalized}@${MAIL_DOMAIN}`
    setSubmitting(true)
    try {
      await createMailbox(emailAddress, password)
      // Straight into the inbox: the password was just typed, no reason to
      // ask for it again on a second, separate login screen.
      const token = await login(emailAddress, password)
      setToken(token.access_token)
      navigate('/inbox', { replace: true })
    } catch (err) {
      setError(describeError(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="mx-auto max-w-sm">
      <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
        <h1 className="text-xl font-semibold text-gray-900">Criar conta</h1>
        <p className="mt-1 text-sm text-gray-500">Escolhe um endereço e uma senha para o proteger.</p>

        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <div>
            <label htmlFor="local-part" className="block text-sm font-medium text-gray-700">
              Endereço
            </label>
            <div className="mt-1 flex items-center overflow-hidden rounded-lg border border-gray-300 transition-colors focus-within:border-indigo-500 focus-within:ring-2 focus-within:ring-indigo-100">
              <input
                id="local-part"
                autoComplete="username"
                required
                value={localPart}
                onChange={(e) => setLocalPart(e.target.value)}
                className="w-full px-3 py-2 text-sm outline-none"
                placeholder="o-que-quiseres"
              />
              <span className="shrink-0 bg-gray-50 px-3 py-2 text-sm text-gray-500">@{MAIL_DOMAIN}</span>
            </div>
          </div>
          <div>
            <label htmlFor="password" className="block text-sm font-medium text-gray-700">
              Senha
            </label>
            <input
              id="password"
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none transition-colors focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
            />
          </div>
          <div>
            <label htmlFor="confirm-password" className="block text-sm font-medium text-gray-700">
              Confirmar senha
            </label>
            <input
              id="confirm-password"
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none transition-colors focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
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
            className="w-full rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-indigo-700 disabled:opacity-50"
          >
            {submitting ? 'A criar…' : 'Criar conta'}
          </button>
        </form>
      </div>
      <p className="mt-4 text-center text-sm text-gray-500">
        Já tens uma conta?{' '}
        <Link to="/login" className="font-medium text-indigo-600 hover:text-indigo-700">
          Consultar caixa
        </Link>
      </p>
    </section>
  )
}

function describeError(err: unknown): string {
  const status = (err as { response?: { status?: number } })?.response?.status
  if (status === 409) return 'Esse endereço já existe. Escolhe outro.'
  if (status === 422) return 'Endereço inválido ou reservado.'
  if (status === 403) return 'A criação de contas está temporariamente fechada.'
  if (status === 429) return 'Demasiados pedidos. Tenta novamente daqui a pouco.'
  return 'Não foi possível criar a conta. Tenta novamente.'
}
