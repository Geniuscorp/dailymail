import { useEffect, useState } from 'react'
import { adminErrorMessage, deleteAdminAttachment, downloadAdminAttachment, listAdminAttachments } from '../../services/adminApi'
import type { AdminAttachment } from '../../types'
import { formatBytes, formatDate, formatNumber } from './format'
import { useAdminQuery } from './hooks'
import { buttonClass, dangerButtonClass, Empty, inputClass, Notice, Pager, saveBlob, useDebounced } from './ui'

const PAGE_SIZE = 50

export default function AttachmentsTab() {
  const [search, setSearch] = useState('')
  const [offset, setOffset] = useState(0)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [notice, setNotice] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  const debouncedSearch = useDebounced(search)

  useEffect(() => setOffset(0), [debouncedSearch])

  const { data, error, loading, reload } = useAdminQuery(
    () => listAdminAttachments({ search: debouncedSearch || undefined, limit: PAGE_SIZE, offset }),
    [debouncedSearch, offset],
    'Não foi possível carregar os anexos.',
  )

  async function download(attachment: AdminAttachment) {
    setBusyId(attachment.id)
    setNotice(null)
    try {
      saveBlob(await downloadAdminAttachment(attachment.id), attachment.original_filename)
    } catch (err) {
      setNotice({ kind: 'error', text: adminErrorMessage(err, 'Não foi possível transferir o anexo.') })
    } finally {
      setBusyId(null)
    }
  }

  async function remove(attachment: AdminAttachment) {
    if (!window.confirm(`Eliminar o anexo "${attachment.original_filename}"?`)) return
    setBusyId(attachment.id)
    setNotice(null)
    try {
      await deleteAdminAttachment(attachment.id)
      setNotice({ kind: 'success', text: 'Anexo eliminado.' })
      reload()
    } catch (err) {
      setNotice({ kind: 'error', text: adminErrorMessage(err, 'Não foi possível eliminar o anexo.') })
    } finally {
      setBusyId(null)
    }
  }

  const pageBytes = (data?.items ?? []).reduce((sum, item) => sum + item.file_size, 0)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Nome do ficheiro ou tipo"
          aria-label="Procurar anexos"
          className={`${inputClass} max-w-sm`}
        />
        <button type="button" onClick={reload} disabled={loading} className={`${buttonClass} ml-auto`}>
          Atualizar
        </button>
      </div>

      {notice && <Notice kind={notice.kind}>{notice.text}</Notice>}
      {error && <Notice kind="error">{error}</Notice>}

      <div className={`overflow-x-auto rounded-2xl border border-gray-200 bg-white shadow-sm transition-opacity ${loading ? 'opacity-60' : ''}`}>
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-50 text-xs text-gray-500">
            <tr>
              <th className="px-4 py-2.5 font-medium">Ficheiro</th>
              <th className="hidden px-3 py-2.5 font-medium sm:table-cell">Tipo</th>
              <th className="px-3 py-2.5 text-right font-medium">Tamanho</th>
              <th className="hidden px-3 py-2.5 font-medium md:table-cell">Mensagem</th>
              <th className="hidden px-3 py-2.5 font-medium md:table-cell">Guardado em</th>
              <th className="px-3 py-2.5" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {(data?.items ?? []).map((attachment) => (
              <tr key={attachment.id} className="hover:bg-gray-50">
                <td className="max-w-[14rem] truncate px-4 py-2.5 font-medium text-gray-900">{attachment.original_filename}</td>
                <td className="hidden px-3 py-2.5 text-gray-500 sm:table-cell">{attachment.mime_type}</td>
                <td className="px-3 py-2.5 text-right tabular-nums">{formatBytes(attachment.file_size)}</td>
                <td className="hidden px-3 py-2.5 text-gray-500 md:table-cell">#{attachment.message_id}</td>
                <td className="hidden px-3 py-2.5 text-gray-500 md:table-cell">{formatDate(attachment.created_at)}</td>
                <td className="px-3 py-2.5">
                  <div className="flex justify-end gap-2">
                    <button type="button" disabled={busyId !== null} className={buttonClass} onClick={() => void download(attachment)}>
                      Transferir
                    </button>
                    <button type="button" disabled={busyId !== null} className={dangerButtonClass} onClick={() => void remove(attachment)}>
                      Eliminar
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {data && data.items.length === 0 && <Empty>Sem anexos.</Empty>}
      </div>

      {data && (
        <p className="text-xs text-gray-500">
          {formatNumber(data.total)} anexo(s) · {formatBytes(pageBytes)} nesta página
        </p>
      )}
      {data && <Pager total={data.total} limit={PAGE_SIZE} offset={offset} onChange={setOffset} />}
    </div>
  )
}
