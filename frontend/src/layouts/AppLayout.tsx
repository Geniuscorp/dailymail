import type { ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { clearToken, getToken } from '../services/session'

export default function AppLayout({ children }: { children: ReactNode }) {
  const navigate = useNavigate()
  const loggedIn = getToken() !== null

  function logout() {
    clearToken()
    navigate('/login', { replace: true })
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-4 py-3">
          <Link to="/" className="text-lg font-semibold text-gray-900">
            DailyMail
          </Link>
          {loggedIn && (
            <button
              type="button"
              onClick={logout}
              className="rounded-md px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100"
            >
              Sair
            </button>
          )}
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-4 py-6">{children}</main>
    </div>
  )
}
