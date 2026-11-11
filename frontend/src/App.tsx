import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import AppLayout from './layouts/AppLayout'
import RedirectIfAuthenticated from './components/RedirectIfAuthenticated'
import RequireAuth from './components/RequireAuth'
import AccountPage from './pages/AccountPage'
import AdminPage from './pages/AdminPage'
import CreateMailboxPage from './pages/CreateMailboxPage'
import HomePage from './pages/HomePage'
import InboxPage from './pages/InboxPage'
import LoginPage from './pages/LoginPage'
import MessagePage from './pages/MessagePage'

function App() {
  return (
    <BrowserRouter>
      <AppLayout>
        <Routes>
          <Route
            path="/"
            element={
              <RedirectIfAuthenticated>
                <HomePage />
              </RedirectIfAuthenticated>
            }
          />
          <Route
            path="/create"
            element={
              <RedirectIfAuthenticated>
                <CreateMailboxPage />
              </RedirectIfAuthenticated>
            }
          />
          <Route
            path="/login"
            element={
              <RedirectIfAuthenticated>
                <LoginPage />
              </RedirectIfAuthenticated>
            }
          />
          <Route path="/admin" element={<AdminPage />} />
          <Route
            path="/inbox"
            element={
              <RequireAuth>
                <InboxPage />
              </RequireAuth>
            }
          />
          <Route
            path="/messages/:id"
            element={
              <RequireAuth>
                <MessagePage />
              </RequireAuth>
            }
          />
          <Route
            path="/account"
            element={
              <RequireAuth>
                <AccountPage />
              </RequireAuth>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AppLayout>
    </BrowserRouter>
  )
}

export default App
