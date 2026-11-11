import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { listMessages } from '../services/api'
import { subscribeToMessageStream } from '../services/messageStream'
import type { MessageSummary } from '../types'

// New mail is pushed over SSE (see messageStream.ts) instead of being
// polled for, so the inbox updates itself the moment a message is stored —
// not on the next tick of a timer. This interval is only a safety net in
// case the stream's connection is stuck (e.g. a proxy buffering it) without
// having visibly dropped; it is deliberately far looser than a poll meant to
// carry the normal case.
const FALLBACK_POLL_INTERVAL_MS = 30000
const PAGE_SIZE = 50
// Matches the backend's hard cap (`Query(..., le=100)` on GET /messages).
const MAX_LIMIT = 100

function formatDate(value: string): string {
  return new Date(value).toLocaleString('pt-PT', { dateStyle: 'short', timeStyle: 'short' })
}

const AVATAR_COLORS = [
  'bg-indigo-100 text-indigo-700',
  'bg-emerald-100 text-emerald-700',
  'bg-amber-100 text-amber-700',
  'bg-rose-100 text-rose-700',
  'bg-sky-100 text-sky-700',
  'bg-violet-100 text-violet-700',
]

function avatarFor(sender: string): { initial: string; className: string } {
  let hash = 0
  for (let i = 0; i < sender.length; i++) hash = (hash * 31 + sender.charCodeAt(i)) >>> 0
  return {
    initial: sender.trim().charAt(0).toUpperCase() || '?',
    className: AVATAR_COLORS[hash % AVATAR_COLORS.length],
  }
}

function EmptyInbox() {
  return (
    <div className="flex flex-col items-center rounded-2xl border border-dashed border-gray-300 py-16 text-center">
      <svg viewBox="0 0 24 24" fill="none" className="h-10 w-10 text-gray-300" aria-hidden="true">
        <rect x="3" y="5" width="18" height="14" rx="3" stroke="currentColor" strokeWidth="1.5" />
        <path
          d="M5 8l6.3 4.2a2 2 0 0 0 2.2 0L20 8"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <p className="mt-3 text-sm text-gray-500">Ainda não recebeste mensagens.</p>
      <p className="text-xs text-gray-400">Vai aparecer aqui assim que chegar — não precisas de atualizar.</p>
    </div>
  )
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
    const unsubscribe = subscribeToMessageStream(() => void load(true))
    const fallback = setInterval(() => void load(true), FALLBACK_POLL_INTERVAL_MS)
    return () => {
      unsubscribe()
      clearInterval(fallback)
    }
  }, [load])

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight text-gray-900">Caixa de entrada</h1>
        <button
          type="button"
          onClick={() => void load()}
          className="rounded-lg px-3 py-1.5 text-sm font-medium text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-900"
        >
          Atualizar
        </button>
      </div>

      {loading && <p className="py-8 text-center text-sm text-gray-400">A carregar…</p>}
      {error && (
        <p role="alert" className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-600">
          {error}
        </p>
      )}
      {!loading && !error && messages.length === 0 && <EmptyInbox />}

      {messages.length > 0 && (
        <ul className="overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm">
          {messages.map((message) => {
            const avatar = avatarFor(message.sender)
            return (
              <li key={message.id} className="border-b border-gray-100 last:border-0">
                <Link to={`/messages/${message.id}`} className="flex items-center gap-3 px-4 py-3.5 transition-colors hover:bg-gray-50">
                  <span
                    className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-semibold ${avatar.className}`}
                    aria-hidden="true"
                  >
                    {avatar.initial}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-baseline justify-between gap-4">
                      <span className={`truncate text-sm ${message.is_read ? 'text-gray-600' : 'font-semibold text-gray-900'}`}>
                        {message.sender}
                      </span>
                      <time className="shrink-0 text-xs text-gray-400" dateTime={message.received_at}>
                        {formatDate(message.received_at)}
                      </time>
                    </span>
                    <span className="mt-0.5 flex items-center gap-2">
                      {!message.is_read && (
                        <span aria-label="Não lida" className="h-2 w-2 shrink-0 rounded-full bg-indigo-600" />
                      )}
                      <span className="truncate text-sm text-gray-600">{message.subject || '(sem assunto)'}</span>
                      {message.attachment_count > 0 && (
                        <span className="shrink-0 text-xs text-gray-400">· {message.attachment_count} anexo(s)</span>
                      )}
                    </span>
                  </span>
                </Link>
              </li>
            )
          })}
        </ul>
      )}

      {hasMore && (
        <div className="flex justify-center">
          <button
            type="button"
            onClick={() => setLimit((current) => Math.min(current + PAGE_SIZE, MAX_LIMIT))}
            className="rounded-lg border border-gray-200 bg-white px-4 py-1.5 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50"
          >
            Carregar mais
          </button>
        </div>
      )}
    </section>
  )
}
