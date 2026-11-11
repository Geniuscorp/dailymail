import type { ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import AccountSwitcherPanel from '../components/AccountSwitcherPanel'
import InfoSidebar from '../components/InfoSidebar'
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

  const header = (
    <header className="z-10 shrink-0 border-b border-gray-200 bg-white">
      <div className="flex items-center justify-between px-6 py-3">
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
  )

  if (!loggedIn) {
    return (
      <div className="flex min-h-screen flex-col bg-gray-50">
        {header}
        <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-12">{children}</main>
        <footer className="shrink-0 border-t border-gray-200 px-4 py-3 text-center text-xs text-gray-400">
          <Link to="/admin" className="hover:text-gray-600">
            Administração
          </Link>
        </footer>
      </div>
    )
  }

  // A full-height application shell, not a page that happens to have
  // sidebars: each pane fills the viewport and scrolls on its own, so a
  // short inbox doesn't leave the panels looking like stray cards adrift in
  // empty space, and the page actually uses the width of the screen instead
  // of floating a narrow column in the middle of it.
  return (
    <div className="flex h-screen flex-col bg-gray-50">
      {header}
      <div className="flex min-h-0 flex-1">
        <aside className="hidden w-64 shrink-0 overflow-y-auto border-r border-gray-200 bg-white lg:block">
          <InfoSidebar />
        </aside>
        <main className="min-w-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-3xl px-6 py-8">{children}</div>
        </main>
        <aside className="hidden w-72 shrink-0 overflow-y-auto border-l border-gray-200 bg-white lg:block">
          <AccountSwitcherPanel />
        </aside>
      </div>
      <footer className="shrink-0 border-t border-gray-200 px-4 py-2 text-center text-xs text-gray-400">
        <Link to="/admin" className="hover:text-gray-600">
          Administração
        </Link>
      </footer>
    </div>
  )
}
