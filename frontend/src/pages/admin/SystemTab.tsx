import { useState, type FormEvent, type ReactNode } from 'react'
import {
  adminErrorMessage,
  changeAdminPassword,
  createAdminUser,
  getAdminMe,
  getAdminSystem,
  listAdminUsers,
  purgeExpiredMessages,
  purgeExpiredSessions,
  setAdminUserStatus,
} from '../../services/adminApi'
import type { AdminSystem } from '../../types'
import { formatBytes, formatDate, formatDuration, formatNumber } from './format'
import { useAdminQuery } from './hooks'
import { buttonClass, Card, inputClass, Notice, PasswordForm, primaryButtonClass, StatusBadge } from './ui'

function Rows({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="divide-y divide-gray-100 text-sm">
      {rows.map(([label, value]) => (
        <div key={label} className="flex items-baseline justify-between gap-4 py-2">
          <dt className="text-gray-500">{label}</dt>
          <dd className="text-right font-medium text-gray-900">{value}</dd>
        </div>
      ))}
    </dl>
  )
}

function yesNo(value: boolean): string {
  return value ? 'Sim' : 'Não'
}

function healthChecks(system: AdminSystem): { ok: boolean; label: string; detail: string }[] {
  const production = system.environment === 'production'
  return [
    {
      ok: production,
      label: 'Ambiente de produção',
      detail: production ? 'ENVIRONMENT=production' : `A correr em "${system.environment}"`,
    },
    {
      ok: !system.debug,
      label: 'Modo debug desligado',
      detail: system.debug ? 'DEBUG está ligado: desliga-o em produção' : 'Desligado',
    },
    {
      ok: system.storage.configured,
      label: 'Armazenamento de anexos configurado',
      detail: system.storage.configured ? `Bucket ${system.storage.bucket}` : 'Sem R2: os anexos são descartados',
    },
    {
      ok: system.inbound.webhook_secret_set,
      label: 'Segredo do webhook de entrada definido',
      detail: system.inbound.webhook_secret_set ? 'Definido' : 'Falta INBOUND_WEBHOOK_SECRET',
    },
    {
      ok: system.protection.rate_limit_enabled,
      label: 'Limite de pedidos ativo',
      detail: system.protection.rate_limit_enabled ? 'Ativo' : 'Desligado: sem proteção contra abuso',
    },
    {
      ok: system.retention.sweep_enabled,
      label: 'Limpeza automática de mensagens',
      detail: system.retention.sweep_enabled
        ? `A cada ${system.retention.sweep_interval_hours} h`
        : 'Desligada: as mensagens expiradas só saem por limpeza manual',
    },
    {
      ok: system.protection.creation_secret_required,
      label: 'Criação de caixas protegida por segredo',
      detail: system.protection.creation_secret_required
        ? 'Ativa'
        : 'Qualquer pessoa pode criar caixas (recomendado: MAILBOX_CREATION_SECRET)',
    },
  ]
}

function AdminsCard() {
  const me = useAdminQuery(getAdminMe, [], 'Não foi possível identificar o administrador.')
  const { data, error, reload } = useAdminQuery(listAdminUsers, [], 'Não foi possível carregar os administradores.')
  const [notice, setNotice] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setNotice(null)
    try {
      await createAdminUser(username.trim(), password)
      setNotice({ kind: 'success', text: `Administrador "${username.trim()}" criado.` })
      setUsername('')
      setPassword('')
      reload()
    } catch (err) {
      setNotice({ kind: 'error', text: adminErrorMessage(err, 'Não foi possível criar o administrador.') })
    } finally {
      setBusy(false)
    }
  }

  async function toggle(id: number, status: 'active' | 'inactive') {
    setNotice(null)
    try {
      await setAdminUserStatus(id, status === 'active' ? 'inactive' : 'active')
      reload()
    } catch (err) {
      setNotice({ kind: 'error', text: adminErrorMessage(err, 'Não foi possível alterar o administrador.') })
    }
  }

  return (
    <Card title="Administradores" subtitle="Quem pode entrar neste painel. As alterações ficam na auditoria.">
      <div className="space-y-4">
        {error && <Notice kind="error">{error}</Notice>}
        {notice && <Notice kind={notice.kind}>{notice.text}</Notice>}

        <ul className="divide-y divide-gray-100 text-sm">
          {(data ?? []).map((user) => (
            <li key={user.id} className="flex items-center justify-between gap-3 py-2">
              <span className="flex items-center gap-2">
                <span className="font-medium text-gray-900">{user.username}</span>
                {me.data?.id === user.id && <span className="text-xs text-gray-500">(tu)</span>}
                <StatusBadge status={user.status} />
              </span>
              {me.data?.id !== user.id && (
                <button type="button" className={buttonClass} onClick={() => void toggle(user.id, user.status)}>
                  {user.status === 'active' ? 'Desativar' : 'Ativar'}
                </button>
              )}
            </li>
          ))}
        </ul>

        <form onSubmit={create} className="grid gap-2 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
          <label className="text-xs font-medium text-gray-600">
            Novo utilizador
            <input
              required
              minLength={3}
              pattern="[A-Za-z0-9_.\-]+"
              title="Letras, números, ponto, hífen e sublinhado"
              autoComplete="off"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              className={`${inputClass} mt-1`}
            />
          </label>
          <label className="text-xs font-medium text-gray-600">
            Senha (mínimo 10 caracteres)
            <input
              required
              type="password"
              minLength={10}
              autoComplete="new-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className={`${inputClass} mt-1`}
            />
          </label>
          <button type="submit" disabled={busy} className={primaryButtonClass}>
            Criar
          </button>
        </form>
      </div>
    </Card>
  )
}

function OwnPasswordCard() {
  const [current, setCurrent] = useState('')
  const [notice, setNotice] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)

  return (
    <Card title="A minha senha" subtitle="Mínimo de 10 caracteres.">
      <div className="space-y-3">
        {notice && <Notice kind={notice.kind}>{notice.text}</Notice>}
        <label className="block text-xs font-medium text-gray-600">
          Senha atual
          <input
            type="password"
            autoComplete="current-password"
            value={current}
            onChange={(event) => setCurrent(event.target.value)}
            className={`${inputClass} mt-1`}
          />
        </label>
        <PasswordForm
          label="Nova senha"
          submitLabel="Alterar"
          minLength={10}
          onSubmit={async (password) => {
            setNotice(null)
            try {
              await changeAdminPassword(current, password)
              setCurrent('')
              setNotice({ kind: 'success', text: 'Senha alterada.' })
            } catch (err) {
              setNotice({ kind: 'error', text: adminErrorMessage(err, 'Não foi possível alterar a senha.') })
            }
          }}
        />
      </div>
    </Card>
  )
}

function MaintenanceCard({ expiredPending }: { expiredPending?: number }) {
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)

  async function run(action: () => Promise<number>, done: (count: number) => string, failure: string) {
    setBusy(true)
    setNotice(null)
    try {
      setNotice({ kind: 'success', text: done(await action()) })
    } catch (err) {
      setNotice({ kind: 'error', text: adminErrorMessage(err, failure) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card title="Manutenção" subtitle="Tarefas que normalmente correm sozinhas. Cada execução fica na auditoria.">
      <div className="space-y-3">
        {notice && <Notice kind={notice.kind}>{notice.text}</Notice>}
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={busy}
            className={buttonClass}
            onClick={() =>
              void run(purgeExpiredMessages, (n) => `${formatNumber(n)} mensagem(ns) expirada(s) eliminada(s).`, 'Não foi possível limpar as mensagens.')
            }
          >
            Limpar mensagens expiradas
            {expiredPending ? ` (${formatNumber(expiredPending)} pendentes)` : ''}
          </button>
          <button
            type="button"
            disabled={busy}
            className={buttonClass}
            onClick={() =>
              void run(purgeExpiredSessions, (n) => `${formatNumber(n)} sessão(ões) expirada(s) removida(s).`, 'Não foi possível limpar as sessões.')
            }
          >
            Limpar sessões expiradas
          </button>
        </div>
      </div>
    </Card>
  )
}

export default function SystemTab({ expiredPending }: { expiredPending?: number }) {
  const { data, error, loading, reload } = useAdminQuery(getAdminSystem, [], 'Não foi possível carregar o estado do sistema.')

  return (
    <div className="space-y-5">
      <div className="flex justify-end">
        <button type="button" onClick={reload} disabled={loading} className={buttonClass}>
          {loading ? 'A atualizar…' : 'Atualizar'}
        </button>
      </div>
      {error && <Notice kind="error">{error}</Notice>}
      {!data && loading && <p className="py-12 text-center text-sm text-gray-500">A carregar…</p>}

      {data && (
        <div className={`space-y-5 transition-opacity ${loading ? 'opacity-60' : ''}`}>
          <Card title="Verificações" subtitle="Configuração que costuma causar problemas quando está errada.">
            <ul className="divide-y divide-gray-100">
              {healthChecks(data).map((check) => (
                <li key={check.label} className="flex items-start gap-3 py-2.5 text-sm">
                  <span
                    aria-hidden="true"
                    className={`mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                      check.ok ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'
                    }`}
                  >
                    {check.ok ? '✓' : '!'}
                  </span>
                  <span>
                    <span className="block font-medium text-gray-900">
                      {check.label}
                      <span className="sr-only">{check.ok ? ' — ok' : ' — atenção'}</span>
                    </span>
                    <span className="block text-xs text-gray-500">{check.detail}</span>
                  </span>
                </li>
              ))}
            </ul>
          </Card>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card title="Aplicação">
              <Rows
                rows={[
                  ['Nome', data.app_name],
                  ['Versão', data.version],
                  ['Ambiente', data.environment],
                  ['Domínio', data.domain],
                  ['Python', data.python],
                  ['Ativa há', formatDuration(data.uptime_seconds)],
                  ['Arrancou em', formatDate(data.started_at)],
                ]}
              />
            </Card>
            <Card title="Dados e armazenamento">
              <Rows
                rows={[
                  ['Base de dados', data.database.dialect],
                  ['Tamanho do ficheiro', formatBytes(data.database.size_bytes)],
                  ['Armazenamento de anexos', data.storage.configured ? `Ligado (${data.storage.bucket})` : 'Não configurado'],
                  ['Tamanho máximo por anexo', `${data.storage.max_attachment_mb} MB`],
                  ['Anexos por mensagem', data.storage.max_attachments_per_message],
                  ['Retenção das mensagens', `${data.retention.days} dias`],
                  ['Limpeza automática', data.retention.sweep_enabled ? `a cada ${data.retention.sweep_interval_hours} h` : 'desligada'],
                ]}
              />
            </Card>
            <Card title="Receção de email">
              <Rows
                rows={[
                  ['Fornecedor', data.inbound.provider],
                  ['Segredo do webhook', data.inbound.webhook_secret_set ? 'Definido' : 'Em falta'],
                  ['Payload máximo', `${data.inbound.max_payload_mb} MB`],
                ]}
              />
            </Card>
            <Card title="Proteção">
              <Rows
                rows={[
                  ['Limite de pedidos', yesNo(data.protection.rate_limit_enabled)],
                  ['Criações por minuto (por IP)', data.protection.create_per_minute],
                  ['Inícios de sessão por minuto (por IP)', data.protection.login_per_minute],
                  ['Webhooks por minuto (por IP)', data.protection.webhook_per_minute],
                  ['Criação exige segredo', yesNo(data.protection.creation_secret_required)],
                  ['Sessão das caixas', `${data.protection.mailbox_session_days} dias`],
                  ['Sessão de administrador', `${data.protection.admin_token_minutes} min`],
                ]}
              />
            </Card>
          </div>

          <Card
            title="Pedidos bloqueados pelo limite"
            subtitle="Desde que o servidor arrancou. Mostra a chave que o servidor usa para contar: se for sempre a mesma para pessoas diferentes, o IP real não está a chegar à aplicação."
          >
            <p className="mb-3 text-sm text-gray-700">
              <strong className="font-semibold text-gray-900">{formatNumber(data.protection.limiter.blocked_total)}</strong>{' '}
              pedido(s) bloqueado(s) · {formatNumber(data.protection.limiter.recent_clients)} cliente(s) ativos no último minuto
            </p>
            {data.protection.limiter.top_blocked.length === 0 ? (
              <p className="py-4 text-center text-sm text-gray-500">Nenhum pedido foi bloqueado.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="text-xs text-gray-500">
                    <tr>
                      <th className="py-2 pr-3 font-medium">Cliente (IP)</th>
                      <th className="py-2 pr-3 font-medium">Ação</th>
                      <th className="py-2 pr-3 text-right font-medium">Bloqueios</th>
                      <th className="py-2 font-medium">Último</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {data.protection.limiter.top_blocked.map((row) => (
                      <tr key={`${row.scope}:${row.client}`}>
                        <td className="py-2 pr-3 font-mono text-xs text-gray-900">{row.client}</td>
                        <td className="py-2 pr-3 text-gray-700">{row.scope}</td>
                        <td className="py-2 pr-3 text-right tabular-nums">{formatNumber(row.count)}</td>
                        <td className="py-2 text-gray-500">{formatDate(row.last_blocked_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-2">
        <AdminsCard />
        <div className="space-y-5">
          <OwnPasswordCard />
          <MaintenanceCard expiredPending={expiredPending} />
        </div>
      </div>
    </div>
  )
}
