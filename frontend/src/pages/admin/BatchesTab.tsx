import { useState } from 'react'
import { adminErrorMessage, listAdminBatches, resetAdminBatchPassword } from '../../services/adminApi'
import { formatDate, formatNumber } from './format'
import { useAdminQuery } from './hooks'
import { buttonClass, Empty, Notice, Pager, PasswordForm } from './ui'

const PAGE_SIZE = 50

export default function BatchesTab() {
  const [offset, setOffset] = useState(0)
  const [openId, setOpenId] = useState<number | null>(null)
  const [notice, setNotice] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)

  const { data, error, loading, reload } = useAdminQuery(
    () => listAdminBatches({ limit: PAGE_SIZE, offset }),
    [offset],
    'Não foi possível carregar os lotes.',
  )

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm text-gray-600">
          Um lote é um conjunto de caixas criadas de uma vez, todas com a mesma senha.
        </p>
        <button type="button" onClick={reload} disabled={loading} className={buttonClass}>
          Atualizar
        </button>
      </div>

      {notice && <Notice kind={notice.kind}>{notice.text}</Notice>}
      {error && <Notice kind="error">{error}</Notice>}

      <ul className={`divide-y divide-gray-100 overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm transition-opacity ${loading ? 'opacity-60' : ''}`}>
        {(data?.items ?? []).map((batch) => (
          <li key={batch.id} className="px-4 py-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="text-sm">
                <p className="font-medium text-gray-900">
                  Lote #{batch.id} · {batch.generation_type === 'custom' ? 'personalizado' : 'aleatório'}
                </p>
                <p className="text-xs text-gray-500">
                  {formatNumber(batch.mailbox_count)} de {formatNumber(batch.quantity)} caixa(s) · criado em{' '}
                  {formatDate(batch.created_at)}
                </p>
              </div>
              <button type="button" className={buttonClass} onClick={() => setOpenId(openId === batch.id ? null : batch.id)}>
                {openId === batch.id ? 'Fechar' : 'Redefinir senha'}
              </button>
            </div>
            {openId === batch.id && (
              <div className="mt-3 rounded-lg bg-gray-50 p-3">
                <PasswordForm
                  label={`Nova senha para as ${batch.mailbox_count} caixas do lote (mínimo 8 caracteres)`}
                  submitLabel="Aplicar ao lote"
                  minLength={8}
                  onSubmit={async (password) => {
                    if (!window.confirm(`Alterar a senha das ${batch.mailbox_count} caixas deste lote?`)) return
                    setNotice(null)
                    try {
                      await resetAdminBatchPassword(batch.id, password)
                      setNotice({ kind: 'success', text: `Senha do lote #${batch.id} alterada.` })
                      setOpenId(null)
                    } catch (err) {
                      setNotice({ kind: 'error', text: adminErrorMessage(err, 'Não foi possível alterar a senha do lote.') })
                    }
                  }}
                />
              </div>
            )}
          </li>
        ))}
      </ul>
      {data && data.items.length === 0 && <Empty>Ainda não foram criados lotes.</Empty>}
      {data && <Pager total={data.total} limit={PAGE_SIZE} offset={offset} onChange={setOffset} />}
    </div>
  )
}
