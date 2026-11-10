const TOKEN_KEY = 'dailymail.token'

// Session storage keeps the token for the current tab only; storage may be
// unavailable (private mode, blocked site data), in which case the user logs in again.
export function getToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token: string): void {
  try {
    sessionStorage.setItem(TOKEN_KEY, token)
  } catch {
    // Without storage the session simply does not persist.
  }
}

export function clearToken(): void {
  try {
    sessionStorage.removeItem(TOKEN_KEY)
  } catch {
    // Nothing to clear if storage is unavailable.
  }
}
