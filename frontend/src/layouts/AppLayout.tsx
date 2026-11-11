import type { ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { logout as logoutRequest } from '../services/api'
import { clearToken, getToken } from '../services/session'

function MailIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-6 w-6" aria-hidden="true">
      <rect x="3" y="5" width="18" height="14" rx="3" className="fill-indigo-600" />
      <path
        d="M5 8l6.3 4.2a2 2 0 0 0 2.2 0L20 8"
        stroke="white"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export default function AppLayout({ children }: { children: ReactNode }) {
  const navigate = useNavigate()
  const loggedIn = getToken() !== null

  async function logout() {
    await logoutRequest()
    clearToken()
    navigate('/login', { replace: true })
  }

  return (
    <div className="flex min-h-screen flex-col bg-gray-50">
      <header className="border-b border-gray-200 bg-white/80 backdrop-blur supports-[backdrop-filter]:bg-white/60 sticky top-0 z-10">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-4 py-3">
          <Link to={loggedIn ? '/inbox' : '/'} className="flex items-center gap-2">
            <MailIcon />
            <span className="text-lg font-semibold tracking-tight text-gray-900">DailyMail</span>
          </Link>
          <div className="flex items-center gap-1">
            {loggedIn && (
              <>
                <Link
                  to="/account"
                  className="rounded-lg px-3 py-1.5 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-100 hover:text-gray-900"
                >
                  Definições
                </Link>
                <button
                  type="button"
                  onClick={() => void logout()}
                  className="rounded-lg px-3 py-1.5 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-100 hover:text-gray-900"
                >
                  Sair
                </button>
              </>
            )}
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-8">{children}</main>
      <footer className="border-t border-gray-200 px-4 py-4 text-center text-xs text-gray-400">
        <Link to="/admin" className="hover:text-gray-600">
          Administração
        </Link>
      </footer>
    </div>
  )
}
