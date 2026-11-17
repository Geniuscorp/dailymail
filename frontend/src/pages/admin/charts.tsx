import { useState } from 'react'
import type { DailyPoint } from '../../types'
import { formatBytes, formatDay, formatNumber, percent } from './format'

// Categorical slots 1-2 of the reference palette and a recessive neutral.
export const SERIES_BLUE = '#2a78d6'
export const SERIES_ORANGE = '#eb6834'
export const NEUTRAL = '#9ca3af'

type Metric = 'messages' | 'mailboxes' | 'attachments' | 'attachment_bytes'

const METRICS: { key: Metric; label: string; format: (value: number) => string }[] = [
  { key: 'messages', label: 'Mensagens recebidas', format: formatNumber },
  { key: 'mailboxes', label: 'Caixas criadas', format: formatNumber },
  { key: 'attachments', label: 'Anexos guardados', format: formatNumber },
  { key: 'attachment_bytes', label: 'Armazenamento novo', format: formatBytes },
]

// Smallest "round" axis maximum at or above the data whose midpoint gridline is also round.
function niceMax(value: number): number {
  if (value <= 10) return Math.max(2, Math.ceil(value / 2) * 2)
  const magnitude = 10 ** Math.floor(Math.log10(value))
  const step = [1, 1.2, 1.4, 1.6, 2, 2.4, 3, 4, 5, 6, 8, 10].find((candidate) => candidate * magnitude >= value) ?? 10
  return step * magnitude
}

function axisLabel(metric: Metric, value: number): string {
  if (metric === 'attachment_bytes') return formatBytes(value)
  return value >= 10_000 ? `${Math.round(value / 1000)}K` : formatNumber(value)
}

export function DailyChart({ series }: { series: DailyPoint[] }) {
  const [metric, setMetric] = useState<Metric>('messages')
  const [view, setView] = useState<'chart' | 'table'>('chart')
  const [hover, setHover] = useState<number | null>(null)

  const config = METRICS.find((m) => m.key === metric) ?? METRICS[0]
  const values = series.map((point) => point[metric])
  const max = niceMax(Math.max(...values, 1))
  const total = values.reduce((sum, value) => sum + value, 0)
  const ticks = [max, max / 2, 0]

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-1" role="tablist" aria-label="Métrica">
          {METRICS.map((item) => (
            <button
              key={item.key}
              type="button"
              role="tab"
              aria-selected={metric === item.key}
              onClick={() => setMetric(item.key)}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                metric === item.key ? 'bg-indigo-600 text-white' : 'text-gray-600 hover:bg-gray-100'
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={() => setView(view === 'chart' ? 'table' : 'chart')}
          className="rounded-lg px-3 py-1.5 text-sm text-gray-500 hover:bg-gray-100"
        >
          {view === 'chart' ? 'Ver tabela' : 'Ver gráfico'}
        </button>
      </div>

      <p className="mb-3 text-xs text-gray-500">
        {config.label} por dia · total no período:{' '}
        <strong className="font-semibold text-gray-900">{config.format(total)}</strong>
      </p>

      {view === 'table' ? (
        <div className="max-h-72 overflow-auto rounded-lg border border-gray-200">
          <table className="w-full text-left text-sm">
            <thead className="sticky top-0 bg-gray-50 text-xs text-gray-500">
              <tr>
                <th className="px-3 py-2 font-medium">Dia</th>
                {METRICS.map((item) => (
                  <th key={item.key} className="px-3 py-2 text-right font-medium">
                    {item.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {[...series].reverse().map((point) => (
                <tr key={point.date}>
                  <td className="px-3 py-1.5 text-gray-700">{formatDay(point.date)}</td>
                  {METRICS.map((item) => (
                    <td key={item.key} className="px-3 py-1.5 text-right tabular-nums text-gray-900">
                      {item.format(point[item.key])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div>
          <div className="relative flex h-48 pl-14">
            <div className="pointer-events-none absolute inset-y-0 left-0 right-0">
              {ticks.map((tick, index) => (
                <div key={tick} className="absolute left-0 right-0" style={{ top: `${index * 50}%` }}>
                  <span className="absolute -top-2 left-0 w-12 text-right text-[11px] tabular-nums text-gray-500">
                    {axisLabel(metric, tick)}
                  </span>
                  <div className="ml-14 border-t border-gray-100" />
                </div>
              ))}
            </div>

            <div className="relative z-10 flex h-full flex-1 items-end gap-0.5" onPointerLeave={() => setHover(null)}>
              {series.map((point, index) => {
                const value = point[metric]
                const height = value > 0 ? Math.max((value / max) * 100, 1.5) : 0
                return (
                  <button
                    key={point.date}
                    type="button"
                    aria-label={`${formatDay(point.date)}: ${config.format(value)}`}
                    onPointerEnter={() => setHover(index)}
                    onFocus={() => setHover(index)}
                    onBlur={() => setHover(null)}
                    className="flex h-full min-w-0 flex-1 items-end justify-center outline-none"
                  >
                    <span
                      className="block w-full max-w-6 rounded-t-[4px] transition-opacity"
                      style={{
                        height: `${height}%`,
                        backgroundColor: SERIES_BLUE,
                        opacity: hover === null || hover === index ? 1 : 0.55,
                      }}
                    />
                  </button>
                )
              })}

              {hover !== null && (
                <div
                  className="pointer-events-none absolute top-0 z-20 -translate-x-1/2 rounded-lg border border-gray-200 bg-white px-3 py-2 shadow-md"
                  style={{ left: `${Math.min(Math.max(((hover + 0.5) / series.length) * 100, 12), 88)}%` }}
                >
                  <p className="text-sm font-semibold tabular-nums text-gray-900">{config.format(values[hover])}</p>
                  <p className="text-xs text-gray-500">{formatDay(series[hover].date)}</p>
                </div>
              )}
            </div>
          </div>
          <div className="mt-2 flex justify-between pl-14 text-[11px] text-gray-500">
            <span>{formatDay(series[0].date)}</span>
            <span>{formatDay(series[Math.floor(series.length / 2)].date)}</span>
            <span>{formatDay(series[series.length - 1].date)}</span>
          </div>
        </div>
      )}
    </div>
  )
}

export interface RankedItem {
  key: string | number
  label: string
  count: number
  detail?: string
}

export function RankedBars({
  items,
  empty,
  onSelect,
}: {
  items: RankedItem[]
  empty: string
  onSelect?: (item: RankedItem) => void
}) {
  if (items.length === 0) return <p className="py-6 text-center text-sm text-gray-500">{empty}</p>
  const max = Math.max(...items.map((item) => item.count), 1)

  return (
    <ul className="space-y-3">
      {items.map((item) => {
        const body = (
          <>
            <span className="flex items-baseline justify-between gap-3 text-sm">
              <span className="truncate text-gray-800">{item.label}</span>
              <span className="shrink-0 tabular-nums font-semibold text-gray-900">
                {formatNumber(item.count)}
                {item.detail && <span className="ml-2 text-xs font-normal text-gray-500">{item.detail}</span>}
              </span>
            </span>
            <span className="mt-1 block h-2 rounded-full bg-gray-100">
              <span
                className="block h-2 rounded-full"
                style={{ width: `${(item.count / max) * 100}%`, backgroundColor: SERIES_BLUE }}
              />
            </span>
          </>
        )
        return (
          <li key={item.key}>
            {onSelect ? (
              <button
                type="button"
                onClick={() => onSelect(item)}
                className="block w-full rounded-lg text-left hover:bg-gray-50"
              >
                {body}
              </button>
            ) : (
              body
            )}
          </li>
        )
      })}
    </ul>
  )
}

export function SegmentedBar({ parts }: { parts: { label: string; value: number; color: string }[] }) {
  const total = parts.reduce((sum, part) => sum + part.value, 0)
  const summary = parts.map((part) => `${part.label}: ${part.value}`).join(', ')

  return (
    <div>
      <div className="flex h-2 gap-0.5 overflow-hidden rounded-full bg-gray-100" role="img" aria-label={summary}>
        {parts
          .filter((part) => part.value > 0)
          .map((part) => (
            <span
              key={part.label}
              title={`${part.label}: ${formatNumber(part.value)} (${percent(part.value, total)})`}
              style={{ width: `${(part.value / total) * 100}%`, backgroundColor: part.color }}
            />
          ))}
      </div>
      <ul className="mt-4 space-y-2">
        {parts.map((part) => (
          <li key={part.label} className="flex items-center gap-2 text-sm">
            <span className="h-2.5 w-2.5 shrink-0 rounded-sm" style={{ backgroundColor: part.color }} aria-hidden="true" />
            <span className="text-gray-600">{part.label}</span>
            <span className="ml-auto tabular-nums font-semibold text-gray-900">
              {formatNumber(part.value)}
              <span className="ml-1 text-xs font-normal text-gray-500">{percent(part.value, total)}</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
