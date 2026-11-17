import { useEffect, useState } from 'react'
import {
  adminErrorMessage,
  bulkAdminMailboxStatus,
  clearAdminMailboxMessages,
  deleteAdminMailbox,
  exportAdminMailboxes,
  getAdminMailbox,
  listAdminMailboxes,
  resetAdminMailboxPassword,
  revokeAdminMailboxSessions,
  updateAdminMailboxStatus,
} from '../../services/adminApi'
import type { MailboxStatus } from '../../types'
import { formatBytes, formatDate, formatNumber } from './format'
import { useAdminQuery } from './hooks'
import {
  buttonClass,
  Card,
  dangerButtonClass,
  Drawer,
  Empty,
  inputClass,
  Notice,
  Pager,
  PasswordForm,
  saveBlob,
  selectClass,
  StatusBadge,
  useDebounced,
} from './ui'

const PAGE_SIZE = 50

function MailboxDrawer({
  id,
  onClose,
  onChanged,
  onViewMessages,
}: {
  id: number
  onClose: () => void
  onChanged: () => void
  onViewMessages: (mailboxId: number) => void
}) {
  const { data, error, reload } = useAdminQuery(() => getAdminMailbox(id), [id], 'Não foi possível carregar a caixa.')
  const [feedback, setFeedback] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)

  async function run(action: () => Promise<string>, failure: string) {
    setBusy(true)
    setFeedback(null)
    try {
      setFeedback({ kind: 'success', text: await action() })
      reload()
      onChanged()
    } catch (err) {
      setFeedback({ kind: 'error', text: adminErrorMessage(err, failure) })
    } finally {
      setBusy(false)
    }
  }

  const blocked = data?.status === 'blocked'

  return (
    <Drawer title={data?.email_address ?? 'Caixa'} onClose={onClose}>
      {error && <Notice kind="error">{error}</Notice>}
      {feedback && <Notice kind={feedback.kind}>{feedback.text}</Notice>}
      {!data && !error && <p className="text-sm text-gray-500">A carregar…</p>}

      {data && (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <StatusBadge status={data.status} />
            <span className="text-xs text-gray-500">
              #{data.id} · criada em {formatDate(data.created_at)}
              {data.batch_id !== null && ` · lote ${data.batch_id}`}
            </span>
            <button
              type="button"
              className="ml-auto text-xs text-indigo-600 hover:underline"
              onClick={() => void navigator.clipboard?.writeText(data.email_address)}
            >
              Copiar endereço
            </button>
          </div>

          <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
            {[
              ['Mensagens', formatNumber(data.message_count)],
              ['Por ler', formatNumber(data.unread_count)],
              ['Anexos', formatNumber(data.attachment_count)],
              ['Armazenamento', formatBytes(data.storage_bytes)],
              ['Sessões ativas', formatNumber(data.live_sessions)],
              ['Última mensagem', formatDate(data.last_message_at)],
            ].map(([label, value]) => (
              <div key={label} className="rounded-lg bg-gray-50 p-3">
                <dt className="text-xs text-gray-500">{label}</dt>
                <dd className="mt-0.5 font-semibold text-gray-900">{value}</dd>
              </div>
            ))}
          </dl>

          <div className="flex flex-wrap gap-2">
            {data.status !== 'deleted' && (
              <button
                type="button"
                disabled={busy}
                className={buttonClass}
                onClick={() =>
                  void run(async () => {
                    await updateAdminMailboxStatus(data.id, blocked ? 'active' : 'blocked')
                    return blocked ? 'Caixa reativada.' : 'Caixa bloqueada.'
                  }, 'Não foi possível alterar o estado.')
                }
              >
                {blocked ? 'Reativar' : 'Bloquear'}
              </button>
            )}
            <button
              type="button"
              disabled={busy}
              className={buttonClass}
              onClick={() =>
                void run(
                  async () => `${await revokeAdminMailboxSessions(data.id)} sessão(ões) terminada(s).`,
                  'Não foi possível terminar as sessões.',
                )
              }
            >
              Terminar sessões
            </button>
            <button type="button" className={buttonClass} onClick={() => onViewMessages(data.id)}>
              Ver mensagens
            </button>
          </div>

          <Card title="Redefinir senha" subtitle="Termina também todas as sessões desta caixa.">
            <PasswordForm
              label="Nova senha (mínimo 8 caracteres)"
              submitLabel="Redefinir"
              minLength={8}
              onSubmit={(password) =>
                run(async () => {
                  await resetAdminMailboxPassword(data.id, password)
                  return 'Senha redefinida.'
                }, 'Não foi possível redefinir a senha.')
              }
            />
          </Card>

          <Card title="Mensagens recentes">
            {data.recent_messages.length === 0 ? (
              <Empty>Esta caixa ainda não recebeu mensagens.</Empty>
            ) : (
              <ul className="divide-y divide-gray-100">
                {data.recent_messages.map((message) => (
                  <li key={message.id} className="py-2 text-sm">
                    <p className="truncate font-medium text-gray-900">{message.subject || '(sem assunto)'}</p>
                    <p className="truncate text-xs text-gray-500">
                      {message.sender} · {formatDate(message.received_at)}
                      {message.attachment_count > 0 && ` · ${message.attachment_count} anexo(s)`}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Zona de risco">
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                disabled={busy || data.message_count === 0}
                className={dangerButtonClass}
                onClick={() => {
                  if (!window.confirm(`Eliminar as ${data.message_count} mensagens desta caixa e os seus anexos?`)) return
                  void run(
                    async () => `${await clearAdminMailboxMessages(data.id)} mensagem(ns) eliminada(s).`,
                    'Não foi possível eliminar as mensagens.',
                  )
                }}
              >
                Esvaziar caixa
              </button>
              <button
                type="button"
                disabled={busy || data.status === 'deleted'}
                className={dangerButtonClass}
                onClick={() => {
                  if (!window.confirm('Eliminar esta conta? Deixa de funcionar e as sessões são terminadas.')) return
                  void run(async () => {
                    await deleteAdminMailbox(data.id)
                    return 'Conta eliminada.'
                  }, 'Não foi possível eliminar a conta.')
                }}
              >
                Eliminar conta
              </button>
            </div>
          </Card>
        </>
      )}
    </Drawer>
  )
}

export default function MailboxesTab({
  focusId,
  onFocusHandled,
  onViewMessages,
}: {
  focusId: number | null
  onFocusHandled: () => void
  onViewMessages: (mailboxId: number) => void
}) {
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<MailboxStatus | ''>('')
  const [offset, setOffset] = useState(0)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [detailId, setDetailId] = useState<number | null>(null)
  const [notice, setNotice] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const debouncedSearch = useDebounced(search)

  useEffect(() => {
    if (focusId !== null) {
      setDetailId(focusId)
      onFocusHandled()
    }
  }, [focusId, onFocusHandled])

  useEffect(() => setOffset(0), [debouncedSearch, status])

  const { data, error, loading, reload } = useAdminQuery(
    () =>
      listAdminMailboxes({
        search: debouncedSearch || undefined,
        status: status || undefined,
        limit: PAGE_SIZE,
        offset,
      }),
    [debouncedSearch, status, offset],
    'Não foi possível carregar as caixas.',
  )

  const items = data?.items ?? []
  const allSelected = items.length > 0 && items.every((item) => selected.has(item.id))

  function toggle(id: number) {
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function bulk(target: MailboxStatus) {
    const verb = { active: 'reativar', blocked: 'bloquear', deleted: 'eliminar' }[target]
    if (!window.confirm(`Queres ${verb} ${selected.size} caixa(s)?`)) return
    setBusy(true)
    setNotice(null)
    try {
      const affected = await bulkAdminMailboxStatus([...selected], target)
      setNotice({ kind: 'success', text: `${affected} caixa(s) atualizada(s).` })
      setSelected(new Set())
      reload()
    } catch (err) {
      setNotice({ kind: 'error', text: adminErrorMessage(err, 'Não foi possível atualizar as caixas.') })
    } finally {
      setBusy(false)
    }
  }

  async function exportCsv() {
    setBusy(true)
    setNotice(null)
    try {
      saveBlob(await exportAdminMailboxes({ search: debouncedSearch || undefined, status: status || undefined }), 'caixas.csv')
    } catch (err) {
      setNotice({ kind: 'error', text: adminErrorMessage(err, 'Não foi possível exportar.') })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Procurar por endereço"
          aria-label="Procurar caixas"
          className={`${inputClass} max-w-xs`}
        />
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value as MailboxStatus | '')}
          aria-label="Filtrar por estado"
          className={selectClass}
        >
          <option value="">Todos os estados</option>
          <option value="active">Ativas</option>
          <option value="blocked">Bloqueadas</option>
          <option value="deleted">Eliminadas</option>
        </select>
        <button type="button" disabled={busy} onClick={() => void exportCsv()} className={`${buttonClass} ml-auto`}>
          Exportar CSV
        </button>
      </div>

      {selected.size > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-xl bg-indigo-50 px-4 py-2.5 text-sm text-indigo-900">
          <span className="font-medium">{selected.size} selecionada(s)</span>
          <button type="button" disabled={busy} className={buttonClass} onClick={() => void bulk('blocked')}>
            Bloquear
          </button>
          <button type="button" disabled={busy} className={buttonClass} onClick={() => void bulk('active')}>
            Reativar
          </button>
          <button type="button" disabled={busy} className={dangerButtonClass} onClick={() => void bulk('deleted')}>
            Eliminar
          </button>
          <button type="button" className="ml-auto text-xs underline" onClick={() => setSelected(new Set())}>
            Limpar seleção
          </button>
        </div>
      )}

      {notice && <Notice kind={notice.kind}>{notice.text}</Notice>}
      {error && <Notice kind="error">{error}</Notice>}

      <div className={`overflow-x-auto rounded-2xl border border-gray-200 bg-white shadow-sm transition-opacity ${loading ? 'opacity-60' : ''}`}>
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-50 text-xs text-gray-500">
            <tr>
              <th className="w-10 px-4 py-2.5">
                <input
                  type="checkbox"
                  aria-label="Selecionar todas desta página"
                  checked={allSelected}
                  onChange={() => setSelected(allSelected ? new Set() : new Set(items.map((item) => item.id)))}
                />
              </th>
              <th className="px-3 py-2.5 font-medium">Endereço</th>
              <th className="px-3 py-2.5 font-medium">Estado</th>
              <th className="px-3 py-2.5 text-right font-medium">Mensagens</th>
              <th className="hidden px-3 py-2.5 font-medium sm:table-cell">Lote</th>
              <th className="hidden px-3 py-2.5 font-medium md:table-cell">Criada em</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {items.map((mailbox) => (
              <tr key={mailbox.id} className="hover:bg-gray-50">
                <td className="px-4 py-2.5">
                  <input
                    type="checkbox"
                    aria-label={`Selecionar ${mailbox.email_address}`}
                    checked={selected.has(mailbox.id)}
                    onChange={() => toggle(mailbox.id)}
                  />
                </td>
                <td className="max-w-[16rem] px-3 py-2.5">
                  <button
                    type="button"
                    onClick={() => setDetailId(mailbox.id)}
                    className="block max-w-full truncate text-left font-medium text-gray-900 hover:text-indigo-700"
                  >
                    {mailbox.email_address}
                  </button>
                </td>
                <td className="px-3 py-2.5">
                  <StatusBadge status={mailbox.status} />
                </td>
                <td className="px-3 py-2.5 text-right tabular-nums">{formatNumber(mailbox.message_count)}</td>
                <td className="hidden px-3 py-2.5 text-gray-500 sm:table-cell">{mailbox.batch_id ?? '—'}</td>
                <td className="hidden px-3 py-2.5 text-gray-500 md:table-cell">{formatDate(mailbox.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {data && items.length === 0 && <Empty>Sem resultados.</Empty>}
      </div>

      {data && <p className="text-xs text-gray-500">{formatNumber(data.total)} caixa(s)</p>}
      {data && <Pager total={data.total} limit={PAGE_SIZE} offset={offset} onChange={setOffset} />}

      {detailId !== null && (
        <MailboxDrawer
          id={detailId}
          onClose={() => setDetailId(null)}
          onChanged={reload}
          onViewMessages={(mailboxId) => {
            setDetailId(null)
            onViewMessages(mailboxId)
          }}
        />
      )}
    </div>
  )
}
