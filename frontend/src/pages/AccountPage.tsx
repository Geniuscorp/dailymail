import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { deleteAccount, updatePassword } from '../services/api'
import { clearToken } from '../services/session'

function ChangePasswordForm() {
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setSuccess(false)

    if (newPassword.length < 8) {
      setError('A nova senha precisa de pelo menos 8 caracteres.')
      return
    }
    if (newPassword !== confirmPassword) {
      setError('As senhas não coincidem.')
      return
    }

    setSubmitting(true)
    try {
      await updatePassword(currentPassword, newPassword)
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
      setSuccess(true)
    } catch (err) {
      const status = (err as { response?: { status?: number } })?.response?.status
      setError(status === 401 ? 'Senha atual incorreta.' : 'Não foi possível mudar a senha.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4 rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
      <div>
        <h2 className="text-base font-semibold text-gray-900">Mudar senha</h2>
        <p className="mt-1 text-xs text-gray-500">
          Isto termina a sessão em todos os outros dispositivos; este fica com a sessão ativa.
        </p>
      </div>
      <div>
        <label htmlFor="current-password" className="block text-sm font-medium text-gray-700">
          Senha atual
        </label>
        <input
          id="current-password"
          type="password"
          autoComplete="current-password"
          required
          value={currentPassword}
          onChange={(e) => setCurrentPassword(e.target.value)}
          className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none transition-colors focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
        />
      </div>
      <div>
        <label htmlFor="new-password" className="block text-sm font-medium text-gray-700">
          Nova senha
        </label>
        <input
          id="new-password"
          type="password"
          autoComplete="new-password"
          required
          minLength={8}
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none transition-colors focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
        />
      </div>
      <div>
        <label htmlFor="confirm-new-password" className="block text-sm font-medium text-gray-700">
          Confirmar nova senha
        </label>
        <input
          id="confirm-new-password"
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
      {success && <p className="text-sm text-emerald-700">Senha alterada.</p>}
      <button
        type="submit"
        disabled={submitting}
        className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-indigo-700 disabled:opacity-50"
      >
        {submitting ? 'A guardar…' : 'Guardar'}
      </button>
    </form>
  )
}

function DeleteAccountSection() {
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function handleDelete() {
    if (!window.confirm('Apagar esta conta? As mensagens e o endereço deixam de poder ser usados. Esta ação não pode ser desfeita.')) {
      return
    }
    setError(null)
    setBusy(true)
    try {
      await deleteAccount()
      clearToken()
      navigate('/', { replace: true })
    } catch {
      setError('Não foi possível apagar a conta.')
      setBusy(false)
    }
  }

  return (
    <div className="space-y-3 rounded-2xl border border-red-200 bg-white p-6 shadow-sm">
      <div>
        <h2 className="text-base font-semibold text-gray-900">Apagar conta</h2>
        <p className="mt-1 text-xs text-gray-500">
          O endereço fica reservado (não pode ser recriado) e deixa de poder ser usado para entrar.
        </p>
      </div>
      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
      <button
        type="button"
        disabled={busy}
        onClick={() => void handleDelete()}
        className="rounded-lg border border-red-200 px-4 py-2 text-sm font-medium text-red-600 transition-colors hover:bg-red-50 disabled:opacity-50"
      >
        Apagar a minha conta
      </button>
    </div>
  )
}

export default function AccountPage() {
  return (
    <section className="mx-auto max-w-md space-y-5">
      <h1 className="text-2xl font-bold tracking-tight text-gray-900">Definições</h1>
      <ChangePasswordForm />
      <DeleteAccountSection />
    </section>
  )
}
