import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { listMessages } from '../services/api'
import type { MessageSummary } from '../types'

// Polls for new mail without the user having to click "Atualizar": a
// background refresh that fails (e.g. a flaky connection) does not show the
// full-page error or spinner, since the inbox already has content on screen.
const POLL_INTERVAL_MS = 1500
const PAGE_SIZE = 50
// Matches the backend's hard cap (`Query(..., le=100)` on GET /messages).
const MAX_LIMIT = 100

function formatDate(value: string): string {
  return new Date(value).toLocaleString('pt-PT', { dateStyle: 'short', timeStyle: 'short' })
}

export default function InboxPage() {
  const [messages, setMessages] = useState<MessageSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // "Load more" simply asks for a bigger page instead of a true offset: the
  // list is small enough for a personal mailbox, and it keeps a single
  // request shape in common with the background poll (no merge/dedup logic
  // needed between the two).
  const [limit, setLimit] = useState(PAGE_SIZE)
  const [hasMore, setHasMore] = useState(false)
  const hasMessages = useRef(false)

  const load = useCallback(async (background = false) => {
    if (!background) {
      setLoading(true)
      setError(null)
    }
    try {
      const data = await listMessages(limit)
      setMessages(data)
      setHasMore(data.length >= limit && limit < MAX_LIMIT)
      hasMessages.current = true
      setError(null)
    } catch {
      if (!background || !hasMessages.current) {
        setError('Não foi possível carregar as mensagens.')
      }
    } finally {
      if (!background) {
        setLoading(false)
      }
    }
  }, [limit])

  useEffect(() => {
    void load()
    const interval = setInterval(() => void load(true), POLL_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [load])

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Caixa de entrada</h1>
        <button
          type="button"
          onClick={() => void load()}
          className="rounded-md px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100"
        >
          Atualizar
        </button>
      </div>

      {loading && <p className="text-gray-500">A carregar…</p>}
      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
      {!loading && !error && messages.length === 0 && (
        <p className="text-gray-500">Ainda não recebeu mensagens.</p>
      )}

      <ul className="divide-y divide-gray-200 rounded-md border border-gray-200 bg-white">
        {messages.map((message) => (
          <li key={message.id}>
            <Link to={`/messages/${message.id}`} className="block px-4 py-3 hover:bg-gray-50">
              <div className="flex items-baseline justify-between gap-4">
                <span className={`truncate text-sm ${message.is_read ? 'text-gray-600' : 'font-semibold text-gray-900'}`}>
                  {message.sender}
                </span>
                <time className="shrink-0 text-xs text-gray-500" dateTime={message.received_at}>
                  {formatDate(message.received_at)}
                </time>
              </div>
              <div className="mt-1 flex items-center gap-2">
                {!message.is_read && (
                  <span aria-label="Não lida" className="h-2 w-2 shrink-0 rounded-full bg-blue-600" />
                )}
                <span className="truncate text-sm text-gray-800">{message.subject || '(sem assunto)'}</span>
                {message.attachment_count > 0 && (
                  <span className="shrink-0 text-xs text-gray-500">· {message.attachment_count} anexo(s)</span>
                )}
              </div>
            </Link>
          </li>
        ))}
      </ul>

      {hasMore && (
        <div className="flex justify-center">
          <button
            type="button"
            onClick={() => setLimit((current) => Math.min(current + PAGE_SIZE, MAX_LIMIT))}
            className="rounded-md border border-gray-300 px-4 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
          >
            Carregar mais
          </button>
        </div>
      )}
    </section>
  )
}
