import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import AttachmentList from '../components/AttachmentList'
import { deleteMessage, getMessage, setMessageRead } from '../services/api'
import type { MessageDetail } from '../types'

// The sanitised HTML runs in an opaque sandbox: no scripts, no same-origin access,
// and a CSP that blocks remote resources (images, fonts, styles from the network).
const HTML_CSP = "default-src 'none'; img-src data:; style-src 'unsafe-inline'"

function buildSrcDoc(html: string): string {
  return `<!doctype html><html><head><meta charset="utf-8">` +
    `<meta http-equiv="Content-Security-Policy" content="${HTML_CSP}">` +
    `<base target="_blank"><style>body{font-family:system-ui,sans-serif;margin:0;padding:12px;color:#111;}</style>` +
    `</head><body>${html}</body></html>`
}

function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleString('pt-PT', { dateStyle: 'long', timeStyle: 'short' }) : '—'
}

export default function MessagePage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [message, setMessage] = useState<MessageDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const messageId = Number(id)
    if (!Number.isInteger(messageId)) {
      setError('Mensagem inválida.')
      return
    }
    let cancelled = false
    ;(async () => {
      try {
        const detail = await getMessage(messageId)
        if (cancelled) return
        setMessage(detail)
        if (!detail.is_read) {
          const updated = await setMessageRead(messageId, true)
          if (!cancelled) setMessage((current) => (current ? { ...current, is_read: updated.is_read } : current))
        }
      } catch {
        if (!cancelled) setError('Não foi possível abrir a mensagem.')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [id])

  async function toggleRead() {
    if (!message) return
    setBusy(true)
    try {
      const updated = await setMessageRead(message.id, !message.is_read)
      setMessage({ ...message, is_read: updated.is_read })
    } catch {
      setError('Não foi possível atualizar a mensagem.')
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    if (!message || !window.confirm('Eliminar esta mensagem?')) return
    setBusy(true)
    try {
      await deleteMessage(message.id)
      navigate('/inbox', { replace: true })
    } catch {
      setError('Não foi possível eliminar a mensagem.')
      setBusy(false)
    }
  }

  if (error) {
    return (
      <section className="space-y-4">
        <p role="alert" className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-600">{error}</p>
        <Link to="/inbox" className="text-sm font-medium text-indigo-600 hover:text-indigo-700">
          ← Voltar à caixa de entrada
        </Link>
      </section>
    )
  }

  if (!message) {
    return <p className="py-8 text-center text-sm text-gray-400">A carregar…</p>
  }

  return (
    <article className="space-y-4">
      <Link to="/inbox" className="text-sm font-medium text-indigo-600 hover:text-indigo-700">
        ← Voltar à caixa de entrada
      </Link>

      <header className="space-y-2 rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
        <h1 className="text-lg font-semibold text-gray-900">{message.subject || '(sem assunto)'}</h1>
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
          <dt className="text-gray-400">De</dt>
          <dd className="break-all text-gray-700">{message.sender}</dd>
          <dt className="text-gray-400">Para</dt>
          <dd className="break-all text-gray-700">{message.recipient}</dd>
          <dt className="text-gray-400">Recebida</dt>
          <dd className="text-gray-700">{formatDate(message.received_at)}</dd>
          <dt className="text-gray-400">Expira</dt>
          <dd className="text-gray-700">{formatDate(message.expires_at)}</dd>
        </dl>
      </header>

      <div className="overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm">
        {message.html_body_sanitized ? (
          <iframe
            title="Conteúdo da mensagem"
            sandbox="allow-popups allow-popups-to-escape-sandbox"
            srcDoc={buildSrcDoc(message.html_body_sanitized)}
            className="h-[60vh] w-full"
          />
        ) : (
          <pre className="whitespace-pre-wrap break-words p-5 font-sans text-sm text-gray-700">
            {message.text_body || '(sem conteúdo)'}
          </pre>
        )}
      </div>

      <AttachmentList attachments={message.attachments} />

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => void toggleRead()}
          className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-50"
        >
          {message.is_read ? 'Marcar como não lida' : 'Marcar como lida'}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void remove()}
          className="rounded-lg border border-red-200 bg-white px-3 py-1.5 text-sm font-medium text-red-600 transition-colors hover:bg-red-50 disabled:opacity-50"
        >
          Eliminar
        </button>
      </div>
    </article>
  )
}
