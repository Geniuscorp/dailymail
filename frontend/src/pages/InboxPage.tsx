import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listMessages } from '../services/api'
import type { MessageSummary } from '../types'

function formatDate(value: string): string {
  return new Date(value).toLocaleString('pt-PT', { dateStyle: 'short', timeStyle: 'short' })
}

export default function InboxPage() {
  const [messages, setMessages] = useState<MessageSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setMessages(await listMessages())
    } catch {
      setError('Não foi possível carregar as mensagens.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
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
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}
