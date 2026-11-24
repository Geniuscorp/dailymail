import { useEffect, useState, type FormEvent, type ReactNode } from 'react'

export const inputClass =
  'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100'
export const selectClass = inputClass.replace('w-full ', '')
export const buttonClass =
  'rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50'
export const primaryButtonClass =
  'rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-onaccent transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50'
export const dangerButtonClass =
  'rounded-lg border border-red-300 bg-white px-3 py-1.5 text-sm font-medium text-red-700 transition-colors hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50'

export function useDebounced<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(timer)
  }, [value, delayMs])
  return debounced
}

export function Card({
  title,
  subtitle,
  actions,
  children,
}: {
  title?: string
  subtitle?: string
  actions?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm sm:p-5">
      {(title || actions) && (
        <header className="mb-4 flex flex-wrap items-start justify-between gap-2">
          <div>
            {title && <h2 className="text-sm font-semibold text-gray-900">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-gray-500">{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      {children}
    </section>
  )
}

export function StatTile({
  label,
  value,
  hint,
  warn,
}: {
  label: string
  value: ReactNode
  hint?: ReactNode
  warn?: boolean
}) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium text-gray-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold tracking-tight text-gray-900">{value}</p>
      {hint && (
        <p className={`mt-1 text-xs ${warn ? 'font-medium text-amber-700' : 'text-gray-500'}`}>
          {warn && <span aria-hidden="true">⚠ </span>}
          {hint}
        </p>
      )}
    </div>
  )
}

export function Notice({ kind, children }: { kind: 'error' | 'success' | 'info'; children: ReactNode }) {
  const styles = {
    error: 'bg-red-50 text-red-700',
    success: 'bg-emerald-50 text-emerald-800',
    info: 'bg-gray-100 text-gray-700',
  }[kind]
  return (
    <p role={kind === 'error' ? 'alert' : 'status'} className={`rounded-lg px-4 py-2.5 text-sm ${styles}`}>
      {children}
    </p>
  )
}

const STATUS_STYLES: Record<string, string> = {
  active: 'bg-emerald-50 text-emerald-800',
  blocked: 'bg-amber-50 text-amber-800',
  deleted: 'bg-gray-100 text-gray-600',
  inactive: 'bg-gray-100 text-gray-600',
}
const STATUS_LABELS: Record<string, string> = {
  active: 'Ativa',
  blocked: 'Bloqueada',
  deleted: 'Eliminada',
  inactive: 'Inativo',
}

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[status] ?? STATUS_STYLES.deleted}`}>
      {STATUS_LABELS[status] ?? status}
    </span>
  )
}

export function Pager({
  total,
  limit,
  offset,
  onChange,
}: {
  total: number
  limit: number
  offset: number
  onChange: (offset: number) => void
}) {
  if (total <= limit) return null
  const from = offset + 1
  const to = Math.min(offset + limit, total)
  return (
    <div className="flex items-center justify-between gap-3 pt-3 text-sm text-gray-600">
      <span>
        {from}–{to} de {total}
      </span>
      <div className="flex gap-2">
        <button type="button" className={buttonClass} disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>
          Anterior
        </button>
        <button type="button" className={buttonClass} disabled={to >= total} onClick={() => onChange(offset + limit)}>
          Seguinte
        </button>
      </div>
    </div>
  )
}

export function Drawer({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-40">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} aria-hidden="true" />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="absolute inset-y-0 right-0 flex w-full max-w-xl flex-col bg-white shadow-xl"
      >
        <header className="flex items-center justify-between gap-3 border-b border-gray-200 px-5 py-3">
          <h2 className="truncate text-sm font-semibold text-gray-900">{title}</h2>
          <button type="button" onClick={onClose} className={buttonClass}>
            Fechar
          </button>
        </header>
        <div className="flex-1 space-y-5 overflow-y-auto p-5">{children}</div>
      </aside>
    </div>
  )
}

export function PasswordForm({
  label,
  submitLabel,
  minLength,
  onSubmit,
}: {
  label: string
  submitLabel: string
  minLength: number
  onSubmit: (password: string) => Promise<void>
}) {
  const [value, setValue] = useState('')
  const [busy, setBusy] = useState(false)

  async function handle(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    try {
      await onSubmit(value)
      setValue('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={handle} className="flex flex-wrap items-end gap-2">
      <label className="min-w-0 flex-1 text-xs font-medium text-gray-600">
        {label}
        <input
          type="password"
          autoComplete="new-password"
          minLength={minLength}
          required
          value={value}
          onChange={(event) => setValue(event.target.value)}
          className={`${inputClass} mt-1`}
        />
      </label>
      <button type="submit" disabled={busy || value.length < minLength} className={buttonClass}>
        {submitLabel}
      </button>
    </form>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-8 text-center text-sm text-gray-500">{children}</p>
}

export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
