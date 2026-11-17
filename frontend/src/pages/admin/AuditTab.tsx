import { useEffect, useState } from 'react'
import { listAdminAudit } from '../../services/adminApi'
import { ACTION_LABELS, formatDate, formatNumber } from './format'
import { useAdminQuery } from './hooks'
import { buttonClass, Empty, Notice, Pager, selectClass } from './ui'

const PAGE_SIZE = 50
const GROUPS = [
  { value: '', label: 'Tudo' },
  { value: 'admin', label: 'Administradores' },
  { value: 'mailbox', label: 'Caixas' },
  { value: 'message', label: 'Mensagens' },
  { value: 'attachment', label: 'Anexos' },
  { value: 'batch', label: 'Lotes' },
  { value: 'maintenance', label: 'Manutenção' },
]

export default function AuditTab() {
  const [group, setGroup] = useState('')
  const [offset, setOffset] = useState(0)

  useEffect(() => setOffset(0), [group])

  const { data, error, loading, reload } = useAdminQuery(
    () => listAdminAudit({ action: group || undefined, limit: PAGE_SIZE, offset }),
    [group, offset],
    'Não foi possível carregar o registo de auditoria.',
  )

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <select value={group} onChange={(event) => setGroup(event.target.value)} aria-label="Filtrar por tipo" className={selectClass}>
          {GROUPS.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
        <button type="button" onClick={reload} disabled={loading} className={`${buttonClass} ml-auto`}>
          Atualizar
        </button>
      </div>

      {error && <Notice kind="error">{error}</Notice>}

      <div className={`overflow-x-auto rounded-2xl border border-gray-200 bg-white shadow-sm transition-opacity ${loading ? 'opacity-60' : ''}`}>
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-50 text-xs text-gray-500">
            <tr>
              <th className="px-4 py-2.5 font-medium">Quando</th>
              <th className="px-3 py-2.5 font-medium">Administrador</th>
              <th className="px-3 py-2.5 font-medium">Ação</th>
              <th className="hidden px-3 py-2.5 font-medium sm:table-cell">Alvo</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {(data?.items ?? []).map((entry) => (
              <tr key={entry.id}>
                <td className="whitespace-nowrap px-4 py-2.5 text-gray-500">{formatDate(entry.created_at)}</td>
                <td className="px-3 py-2.5 text-gray-900">{entry.admin_username ?? '—'}</td>
                <td className="px-3 py-2.5 text-gray-800">{ACTION_LABELS[entry.action] ?? entry.action}</td>
                <td className="hidden px-3 py-2.5 text-gray-500 sm:table-cell">
                  {entry.target_type}
                  {entry.target_id && ` #${entry.target_id}`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {data && data.items.length === 0 && <Empty>Sem registos.</Empty>}
      </div>

      {data && <p className="text-xs text-gray-500">{formatNumber(data.total)} registo(s)</p>}
      {data && <Pager total={data.total} limit={PAGE_SIZE} offset={offset} onChange={setOffset} />}
    </div>
  )
}
