import { useEffect, useState } from 'react'
import { getAdminOverview } from '../../services/adminApi'
import { DailyChart, NEUTRAL, RankedBars, SegmentedBar, SERIES_BLUE, SERIES_ORANGE } from './charts'
import { formatBytes, formatNumber, percent } from './format'
import { useAdminQuery } from './hooks'
import { buttonClass, Card, Notice, StatTile } from './ui'

const PERIODS = [7, 14, 30, 90]

export default function OverviewTab({ onOpenMailbox }: { onOpenMailbox: (id: number) => void }) {
  const [days, setDays] = useState(30)
  const { data, error, loading, reload } = useAdminQuery(
    () => getAdminOverview(days),
    [days],
    'Não foi possível carregar a visão geral.',
  )

  useEffect(() => {
    const timer = setInterval(reload, 60_000)
    return () => clearInterval(timer)
  }, [reload])

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1" role="group" aria-label="Período">
          {PERIODS.map((period) => (
            <button
              key={period}
              type="button"
              aria-pressed={days === period}
              onClick={() => setDays(period)}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                days === period ? 'bg-indigo-600 text-white' : 'text-gray-600 hover:bg-gray-100'
              }`}
            >
              {period} dias
            </button>
          ))}
        </div>
        <button type="button" onClick={reload} disabled={loading} className={buttonClass}>
          {loading ? 'A atualizar…' : 'Atualizar'}
        </button>
      </div>

      {error && <Notice kind="error">{error}</Notice>}
      {!data && loading && <p className="py-12 text-center text-sm text-gray-500">A carregar…</p>}

      {data && (
        <div className={`space-y-5 transition-opacity ${loading ? 'opacity-60' : ''}`}>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
            <StatTile
              label="Caixas ativas"
              value={formatNumber(data.mailboxes.active)}
              hint={`de ${formatNumber(data.mailboxes.total)} no total`}
            />
            <StatTile
              label="Mensagens"
              value={formatNumber(data.messages.total)}
              hint={`${formatNumber(data.messages.last_24h)} nas últimas 24 h`}
            />
            <StatTile
              label="Por ler"
              value={formatNumber(data.messages.unread)}
              hint={`${percent(data.messages.unread, data.messages.total)} das mensagens`}
            />
            <StatTile
              label="Anexos"
              value={formatNumber(data.attachments.total)}
              hint={`${formatBytes(data.attachments.bytes)} no armazenamento`}
            />
            <StatTile
              label="Sessões ativas"
              value={formatNumber(data.activity.live_sessions)}
              hint={`${formatNumber(data.activity.admins)} administrador(es)`}
            />
            <StatTile
              label="Receberam mail (24 h)"
              value={formatNumber(data.activity.active_mailboxes_24h)}
              hint="caixas distintas"
            />
            <StatTile
              label="Novas caixas"
              value={formatNumber(data.activity.new_mailboxes_24h)}
              hint={`${formatNumber(data.activity.new_mailboxes_7d)} nos últimos 7 dias`}
            />
            <StatTile label="Lotes" value={formatNumber(data.activity.batches)} hint="criados até hoje" />
            <StatTile
              label="A expirar em 7 dias"
              value={formatNumber(data.messages.expiring_soon)}
              hint="mensagens"
            />
            <StatTile
              label="Expiradas por limpar"
              value={formatNumber(data.messages.expired_pending)}
              hint={data.messages.expired_pending > 0 ? 'corre a limpeza em Sistema' : 'tudo em dia'}
              warn={data.messages.expired_pending > 0}
            />
          </div>

          <Card title="Atividade diária" subtitle={`Últimos ${data.days} dias (UTC)`}>
            <DailyChart series={data.series} />
          </Card>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card title="Estado das caixas">
              <SegmentedBar
                parts={[
                  { label: 'Ativas', value: data.mailboxes.active, color: SERIES_BLUE },
                  { label: 'Bloqueadas', value: data.mailboxes.blocked, color: SERIES_ORANGE },
                  { label: 'Eliminadas', value: data.mailboxes.deleted, color: NEUTRAL },
                ]}
              />
            </Card>
            <Card
              title="Anexos por tipo"
              subtitle={`Maior anexo: ${formatBytes(data.attachments.largest_bytes)} · média: ${formatBytes(data.attachments.average_bytes)}`}
            >
              <RankedBars
                empty="Ainda não há anexos."
                items={data.attachment_types.map((item) => ({
                  key: item.mime_type,
                  label: item.mime_type,
                  count: item.count,
                  detail: formatBytes(item.bytes),
                }))}
              />
            </Card>
          </div>

          <div className="grid gap-5 lg:grid-cols-3">
            <Card title="Remetentes mais frequentes" subtitle={`Últimos ${data.days} dias`}>
              <RankedBars
                empty="Sem mensagens neste período."
                items={data.top_senders.map((item) => ({ key: item.label, label: item.label, count: item.count }))}
              />
            </Card>
            <Card title="Domínios de origem" subtitle={`Últimos ${data.days} dias`}>
              <RankedBars
                empty="Sem mensagens neste período."
                items={data.top_sender_domains.map((item) => ({ key: item.label, label: item.label, count: item.count }))}
              />
            </Card>
            <Card title="Caixas mais ativas" subtitle={`Últimos ${data.days} dias · clica para abrir`}>
              <RankedBars
                empty="Sem mensagens neste período."
                onSelect={(item) => onOpenMailbox(Number(item.key))}
                items={data.busiest_mailboxes.map((item) => ({
                  key: item.mailbox_id,
                  label: item.email_address,
                  count: item.count,
                }))}
              />
            </Card>
          </div>
        </div>
      )}
    </div>
  )
}
