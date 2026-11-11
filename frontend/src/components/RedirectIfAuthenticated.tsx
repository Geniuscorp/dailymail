import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { getToken } from '../services/session'

// Mirrors RequireAuth: a signed-in visitor hitting "/", "/login" or
// "/create" should land back in their inbox, not be asked to log in again.
export default function RedirectIfAuthenticated({ children }: { children: ReactNode }) {
  if (getToken()) {
    return <Navigate to="/inbox" replace />
  }
  return <>{children}</>
}
