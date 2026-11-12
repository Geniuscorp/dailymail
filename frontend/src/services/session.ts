const TOKEN_KEY = 'dailymail.token'
const ADMIN_TOKEN_KEY = 'dailymail.admin.token'
const ACCOUNTS_KEY = 'dailymail.accounts'

// localStorage keeps the mailbox token across browser restarts, like
// mail.tm: the password is only needed again at login, not every time the
// inbox is opened. Storage may be unavailable (private mode, blocked site
// data), in which case the user logs in again.
export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token: string): void {
  try {
    localStorage.setItem(TOKEN_KEY, token)
  } catch {
    // Without storage the session simply does not persist.
  }
}

export function clearToken(): void {
  try {
    localStorage.removeItem(TOKEN_KEY)
  } catch {
    // Nothing to clear if storage is unavailable.
  }
}

export interface RememberedAccount {
  email: string
  token: string
}

function readAccounts(): RememberedAccount[] {
  try {
    const raw = localStorage.getItem(ACCOUNTS_KEY)
    const parsed: unknown = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function writeAccounts(accounts: RememberedAccount[]): void {
  try {
    localStorage.setItem(ACCOUNTS_KEY, JSON.stringify(accounts))
  } catch {
    // Without storage the list simply does not persist.
  }
}

// The accounts every login/account-creation in this browser remembered, so
// the account switcher can offer a one-click return instead of asking for
// the password again. Most-recently-used first.
export function listAccounts(): RememberedAccount[] {
  return readAccounts()
}

// Called after every successful login or account creation. Keeps at most
// one entry per email - a fresh login replaces any stale token for it.
export function rememberAccount(email: string, token: string): void {
  const accounts = readAccounts().filter((account) => account.email !== email)
  accounts.unshift({ email, token })
  writeAccounts(accounts)
}

// Removes an account from the switcher list: used when the user explicitly
// forgets it, and when its token turns out to be invalid (expired, revoked
// by logout/password-change/deletion) - keeping it listed would just offer
// a "switch" that fails.
export function forgetAccount(email: string): void {
  writeAccounts(readAccounts().filter((account) => account.email !== email))
}

// Same, but by token rather than email - for the call sites (logout,
// account deletion, the global 401 handler) that know which token just
// became invalid but not necessarily which email it belonged to.
export function forgetAccountByToken(token: string): void {
  writeAccounts(readAccounts().filter((account) => account.token !== token))
}

// The admin token stays in sessionStorage: an admin session must never be
// mistaken for a mailbox session, the two APIs reject each other's tokens,
// and an operator session is not meant to outlive the browser tab.
export function getAdminToken(): string | null {
  try {
    return sessionStorage.getItem(ADMIN_TOKEN_KEY)
  } catch {
    return null
  }
}

export function setAdminToken(token: string): void {
  try {
    sessionStorage.setItem(ADMIN_TOKEN_KEY, token)
  } catch {
    // Without storage the session simply does not persist.
  }
}

export function clearAdminToken(): void {
  try {
    sessionStorage.removeItem(ADMIN_TOKEN_KEY)
  } catch {
    // Nothing to clear if storage is unavailable.
  }
}
