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
    <section className="mx-auto max-w-sm space-y-6">
      <h1 className="text-2xl font-semibold">Criar conta</h1>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="local-part" className="block text-sm font-medium text-gray-700">
            Endereço
          </label>
          <div className="mt-1 flex items-center rounded-md border border-gray-300 focus-within:border-gray-900">
            <input
              id="local-part"
              autoComplete="username"
              required
              value={localPart}
              onChange={(e) => setLocalPart(e.target.value)}
              className="w-full rounded-l-md px-3 py-2 focus:outline-none"
              placeholder="o-que-quiseres"
            />
            <span className="shrink-0 pr-3 text-gray-500">@{MAIL_DOMAIN}</span>
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
            className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 focus:border-gray-900 focus:outline-none"
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
          {submitting ? 'A criar…' : 'Criar conta'}
        </button>
      </form>
      <p className="text-center text-sm text-gray-600">
        Já tens uma conta?{' '}
        <Link to="/login" className="underline">
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
