import { useState, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import AccountSwitcherPanel from '../components/AccountSwitcherPanel'
import InfoSidebar from '../components/InfoSidebar'
import { logout as logoutRequest } from '../services/api'
import { clearToken, forgetAccountByToken, getToken } from '../services/session'

function MenuIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5" aria-hidden="true">
      <path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

function CloseIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5" aria-hidden="true">
      <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

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
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  async function logout() {
    await logoutRequest()
    const token = getToken()
    if (token) forgetAccountByToken(token)
    clearToken()
    navigate('/login', { replace: true })
  }

  const header = (
    <header className="z-20 shrink-0 border-b border-gray-200 bg-white">
      <div className="flex items-center justify-between px-6 py-3">
        <div className="flex items-center gap-1">
          {loggedIn && (
            // Only the sidebars (account info, account switcher) are
            // reachable from here: on a narrow screen they aren't shown
            // beside the inbox, so without this they would be entirely
            // unreachable, not just visually hidden.
            <button
              type="button"
              onClick={() => setMobileMenuOpen(true)}
              aria-label="Abrir menu de conta"
              className="-ml-1.5 rounded-lg p-1.5 text-gray-600 transition-colors hover:bg-gray-100 hover:text-gray-900 lg:hidden"
            >
              <MenuIcon />
            </button>
          )}
          <Link to={loggedIn ? '/inbox' : '/'} className="flex items-center gap-2">
            <MailIcon />
            <span className="text-lg font-semibold tracking-tight text-gray-900">DailyMail</span>
          </Link>
        </div>
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

  // Same two panels the desktop sidebars show, reused as-is: an overlay
  // drawer on screens below `lg`, where there is no room for them beside
  // the inbox. Always unmounted (not just hidden) above `lg`, so resizing
  // back down never leaves it stuck open from stale state.
  const mobileMenu = loggedIn && mobileMenuOpen && (
    <div className="fixed inset-0 z-30 lg:hidden">
      <div className="absolute inset-0 bg-black/30" onClick={() => setMobileMenuOpen(false)} />
      <div className="absolute inset-y-0 left-0 w-80 max-w-[85vw] overflow-y-auto bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
          <span className="text-sm font-semibold text-gray-900">Menu</span>
          <button
            type="button"
            onClick={() => setMobileMenuOpen(false)}
            aria-label="Fechar menu"
            className="rounded-lg p-1.5 text-gray-500 hover:bg-gray-100 hover:text-gray-900"
          >
            <CloseIcon />
          </button>
        </div>
        <div className="divide-y divide-gray-100">
          <AccountSwitcherPanel />
          <InfoSidebar />
        </div>
      </div>
    </div>
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
      {mobileMenu}
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
