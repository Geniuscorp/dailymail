import { useEffect, useState } from 'react'
import {
  adminErrorMessage,
  deleteAdminMessage,
  downloadAdminAttachment,
  getAdminMessage,
  listAdminMessages,
} from '../../services/adminApi'
import type { AdminAttachment } from '../../types'
import { formatBytes, formatDate, formatNumber } from './format'
import { useAdminQuery } from './hooks'
import { buttonClass, Card, dangerButtonClass, Drawer, Empty, inputClass, selectClass, Notice, Pager, saveBlob, useDebounced } from './ui'

const PAGE_SIZE = 50

function MessageDrawer({
  id,
  onClose,
  onDeleted,
  onOpenMailbox,
}: {
  id: number
  onClose: () => void
  onDeleted: () => void
  onOpenMailbox: (mailboxId: number) => void
}) {
  const { data, error } = useAdminQuery(() => getAdminMessage(id), [id], 'Não foi possível carregar a mensagem.')
  const [feedback, setFeedback] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function download(attachment: AdminAttachment) {
    setBusy(true)
    setFeedback(null)
    try {
      saveBlob(await downloadAdminAttachment(attachment.id), attachment.original_filename)
    } catch (err) {
      setFeedback(adminErrorMessage(err, 'Não foi possível transferir o anexo.'))
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    if (!window.confirm('Eliminar esta mensagem e os seus anexos?')) return
    setBusy(true)
    setFeedback(null)
    try {
      await deleteAdminMessage(id)
      onDeleted()
      onClose()
    } catch (err) {
      setFeedback(adminErrorMessage(err, 'Não foi possível eliminar a mensagem.'))
      setBusy(false)
    }
  }

  return (
    <Drawer title={data?.subject || 'Mensagem'} onClose={onClose}>
      {error && <Notice kind="error">{error}</Notice>}
      {feedback && <Notice kind="error">{feedback}</Notice>}
      {!data && !error && <p className="text-sm text-gray-500">A carregar…</p>}

      {data && (
        <>
          <dl className="space-y-1.5 text-sm">
            {[
              ['De', data.sender],
              ['Para', data.recipient],
              ['Recebida', formatDate(data.received_at)],
              ['Expira', formatDate(data.expires_at)],
              ['Estado', data.is_read ? 'Lida' : 'Por ler'],
            ].map(([label, value]) => (
              <div key={label} className="flex gap-3">
                <dt className="w-20 shrink-0 text-gray-500">{label}</dt>
                <dd className="min-w-0 break-words text-gray-900">{value}</dd>
              </div>
            ))}
          </dl>

          <Card title="Conteúdo" subtitle="Texto simples; o HTML não é renderizado no painel.">
            {data.text_body ? (
              <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words text-sm text-gray-800">
                {data.text_body}
              </pre>
            ) : (
              <p className="text-sm text-gray-500">Esta mensagem não tem versão em texto.</p>
            )}
          </Card>

          <Card title={`Anexos (${data.attachments.length})`}>
            {data.attachments.length === 0 ? (
              <p className="text-sm text-gray-500">Sem anexos.</p>
            ) : (
              <ul className="divide-y divide-gray-100">
                {data.attachments.map((attachment) => (
                  <li key={attachment.id} className="flex items-center justify-between gap-3 py-2 text-sm">
                    <span className="min-w-0">
                      <span className="block truncate text-gray-900">{attachment.original_filename}</span>
                      <span className="text-xs text-gray-500">
                        {attachment.mime_type} · {formatBytes(attachment.file_size)}
                      </span>
                    </span>
                    <button type="button" disabled={busy} className={buttonClass} onClick={() => void download(attachment)}>
                      Transferir
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className={buttonClass}
              onClick={() => {
                onClose()
                onOpenMailbox(data.mailbox_id)
              }}
            >
              Abrir caixa
            </button>
            <button type="button" disabled={busy} className={dangerButtonClass} onClick={() => void remove()}>
              Eliminar mensagem
            </button>
          </div>
        </>
      )}
    </Drawer>
  )
}

export default function MessagesTab({
  mailboxId,
  onClearMailbox,
  onOpenMailbox,
}: {
  mailboxId: number | null
  onClearMailbox: () => void
  onOpenMailbox: (mailboxId: number) => void
}) {
  const [search, setSearch] = useState('')
  const [read, setRead] = useState<'' | 'unread'>('')
  const [files, setFiles] = useState<'' | 'with' | 'without'>('')
  const [offset, setOffset] = useState(0)
  const [detailId, setDetailId] = useState<number | null>(null)
  const debouncedSearch = useDebounced(search)

  useEffect(() => setOffset(0), [debouncedSearch, read, files, mailboxId])

  const { data, error, loading, reload } = useAdminQuery(
    () =>
      listAdminMessages({
        search: debouncedSearch || undefined,
        mailbox_id: mailboxId ?? undefined,
        unread: read === 'unread' ? true : undefined,
        has_attachments: files === '' ? undefined : files === 'with',
        limit: PAGE_SIZE,
        offset,
      }),
    [debouncedSearch, mailboxId, read, files, offset],
    'Não foi possível carregar as mensagens.',
  )

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Remetente, destinatário ou assunto"
          aria-label="Procurar mensagens"
          className={`${inputClass} max-w-sm`}
        />
        <select value={read} onChange={(event) => setRead(event.target.value as '' | 'unread')} aria-label="Filtrar por leitura" className={selectClass}>
          <option value="">Lidas e por ler</option>
          <option value="unread">Só por ler</option>
        </select>
        <select value={files} onChange={(event) => setFiles(event.target.value as '' | 'with' | 'without')} aria-label="Filtrar por anexos" className={selectClass}>
          <option value="">Com ou sem anexos</option>
          <option value="with">Com anexos</option>
          <option value="without">Sem anexos</option>
        </select>
        <button type="button" onClick={reload} disabled={loading} className={`${buttonClass} ml-auto`}>
          Atualizar
        </button>
      </div>

      {mailboxId !== null && (
        <div className="flex items-center gap-3 rounded-xl bg-indigo-50 px-4 py-2.5 text-sm text-indigo-900">
          <span>A mostrar só as mensagens da caixa #{mailboxId}.</span>
          <button type="button" className="underline" onClick={() => onOpenMailbox(mailboxId)}>
            Abrir caixa
          </button>
          <button type="button" className="ml-auto underline" onClick={onClearMailbox}>
            Ver todas
          </button>
        </div>
      )}

      {error && <Notice kind="error">{error}</Notice>}

      <ul className={`divide-y divide-gray-100 overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm transition-opacity ${loading ? 'opacity-60' : ''}`}>
        {(data?.items ?? []).map((message) => (
          <li key={message.id}>
            <button
              type="button"
              onClick={() => setDetailId(message.id)}
              className="flex w-full items-center justify-between gap-4 px-4 py-3 text-left hover:bg-gray-50"
            >
              <span className="min-w-0">
                <span className={`block truncate text-sm ${message.is_read ? 'text-gray-700' : 'font-semibold text-gray-900'}`}>
                  {message.subject || '(sem assunto)'}
                </span>
                <span className="block truncate text-xs text-gray-500">
                  {message.sender} → {message.recipient}
                </span>
              </span>
              <span className="shrink-0 text-right text-xs text-gray-500">
                <span className="block">{formatDate(message.received_at)}</span>
                {message.attachment_count > 0 && <span className="block">{message.attachment_count} anexo(s)</span>}
              </span>
            </button>
          </li>
        ))}
      </ul>
      {data && data.items.length === 0 && <Empty>Sem resultados.</Empty>}

      {data && <p className="text-xs text-gray-500">{formatNumber(data.total)} mensagem(ns)</p>}
      {data && <Pager total={data.total} limit={PAGE_SIZE} offset={offset} onChange={setOffset} />}

      {detailId !== null && (
        <MessageDrawer id={detailId} onClose={() => setDetailId(null)} onDeleted={reload} onOpenMailbox={onOpenMailbox} />
      )}
    </div>
  )
}
