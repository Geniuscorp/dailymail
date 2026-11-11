const TOKEN_KEY = 'dailymail.token'
const ADMIN_TOKEN_KEY = 'dailymail.admin.token'

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
