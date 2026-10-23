'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Archive, Check } from 'lucide-react'
import { Badge, FrameworkBadge, type BadgeTone } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { Field, Select } from '@/components/ui/Field'
import { SkeletonText } from '@/components/ui/Skeleton'
import { api } from '@/lib/api'
import { formatDateIt, parseIsoDate, startOfDay } from '@/lib/obligations/dates'
import type { Alert, Severity } from '@/lib/types'

export const SEVERITY_META: Record<Severity, { label: string; tone: BadgeTone }> = {
  CRITICAL: { label: 'Critico', tone: 'bad' },
  HIGH: { label: 'Alto', tone: 'bad' },
  MEDIUM: { label: 'Medio', tone: 'warn' },
  LOW: { label: 'Basso', tone: 'neutral' },
  INFORMATIONAL: { label: 'Informativo', tone: 'neutral' },
}

const SEVERITIES: Severity[] = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFORMATIONAL']

export interface AlertSummaryView {
  total: number
  unread: number
}

/** The backend answers { alerts, total, limit, offset }; older code expected a bare array. Both are accepted. */
export function normaliseAlerts(raw: unknown): Alert[] {
  const list = Array.isArray(raw) ? raw : ((raw as { alerts?: unknown[] } | null)?.alerts ?? [])
  return (list as unknown[]).filter((a): a is Alert => {
    if (!a || typeof a !== 'object') return false
    const x = a as Record<string, unknown>
    return typeof x.id === 'string' && typeof x.title === 'string' && typeof x.severity === 'string'
  })
}

/**
 * The backend summary has `total_unread` and lists of counts; the demo
 * summary has `unread` and records. Only the two totals are used here.
 */
export function normaliseSummary(raw: unknown): AlertSummaryView | null {
  if (!raw || typeof raw !== 'object') return null
  const s = raw as Record<string, unknown>
  const total = typeof s.total === 'number' ? s.total : null
  const unread =
    typeof s.total_unread === 'number' ? s.total_unread : typeof s.unread === 'number' ? s.unread : null
  if (total == null || unread == null) return null
  return { total, unread }
}

function isIsoDate(value: string | undefined): value is string {
  return !!value && /^\d{4}-\d{2}-\d{2}/.test(value)
}

function createdAtLabel(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return new Intl.DateTimeFormat('it-IT', { day: 'numeric', month: 'long', year: 'numeric' }).format(d)
}

function AlertCard({
  alert,
  today,
  busy,
  onRead,
  onDismiss,
}: {
  alert: Alert
  today: Date
  busy: boolean
  onRead: () => void
  onDismiss: () => void
}) {
  const sev = SEVERITY_META[alert.severity] ?? { label: alert.severity, tone: 'neutral' as BadgeTone }
  const deadlinePast = isIsoDate(alert.deadline) && parseIsoDate(alert.deadline.slice(0, 10)) < startOfDay(today)
  return (
    <article
      aria-labelledby={`alert-${alert.id}`}
      className="rounded-lg border border-rule bg-surface px-5 py-4"
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={sev.tone}>{sev.label}</Badge>
        {alert.framework && <FrameworkBadge framework={alert.framework} />}
        {!alert.is_read && <Badge tone="union">Non letto</Badge>}
        <span className="ml-auto text-caption text-ink-3">Creato il {createdAtLabel(alert.created_at)}</span>
      </div>
      <h3 id={`alert-${alert.id}`} className="mt-2 font-sans text-body font-medium text-ink">
        {alert.title}
      </h3>
      {alert.description && <p className="mt-1 text-small text-ink-2">{alert.description}</p>}
      {alert.actions_required && alert.actions_required.length > 0 && (
        <ol className="mt-2 list-decimal space-y-0.5 pl-5 text-small text-ink">
          {alert.actions_required.map((a) => (
            <li key={a}>{a}</li>
          ))}
        </ol>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        <span className="text-small text-ink-2">
          <span className="text-ink-3">Scadenza: </span>
          {isIsoDate(alert.deadline) ? formatDateIt(alert.deadline.slice(0, 10)) : alert.deadline || 'non indicata'}
        </span>
        {deadlinePast && <Badge tone="bad">Scadenza superata</Badge>}
        <div className="ml-auto flex flex-wrap gap-2">
          {!alert.is_read && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={busy}
              iconLeft={<Check className="h-4 w-4" aria-hidden="true" />}
              onClick={onRead}
            >
              Segna come letto
            </Button>
          )}
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={busy}
            iconLeft={<Archive className="h-4 w-4" aria-hidden="true" />}
            onClick={onDismiss}
          >
            Archivia l’avviso
          </Button>
        </div>
      </div>
    </article>
  )
}

/**
 * The organization's alerts from /api/v1/alerts with the summary from
 * /api/v1/alerts/summary. Mark as read and dismiss use the PATCH endpoints
 * of src/api/routers/alerts.py.
 */
export function AlertsTab({ onUnreadChange, today = new Date() }: { onUnreadChange?: (n: number) => void; today?: Date }) {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [summary, setSummary] = useState<AlertSummaryView | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [severity, setSeverity] = useState<Severity | ''>('')
  const [readState, setReadState] = useState<'all' | 'unread' | 'read'>('all')
  const [busy, setBusy] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [rawAlerts, rawSummary] = await Promise.all([
        api.get<unknown>('/api/v1/alerts?limit=50&offset=0'),
        api.get<unknown>('/api/v1/alerts/summary').catch(() => null),
      ])
      const list = normaliseAlerts(rawAlerts).filter((a) => !a.is_dismissed)
      setAlerts(list)
      const s = normaliseSummary(rawSummary) ?? { total: list.length, unread: list.filter((a) => !a.is_read).length }
      setSummary(s)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Gli avvisi non sono disponibili al momento. Riprova tra un minuto.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (summary) onUnreadChange?.(summary.unread)
  }, [summary, onUnreadChange])

  const markRead = async (alert: Alert) => {
    setBusy(alert.id)
    setError('')
    try {
      await api.fetch(`/api/v1/alerts/${alert.id}/read`, { method: 'PATCH' })
      setAlerts((prev) => prev.map((a) => (a.id === alert.id ? { ...a, is_read: true } : a)))
      setSummary((prev) => (prev ? { ...prev, unread: Math.max(0, prev.unread - (alert.is_read ? 0 : 1)) } : prev))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'L’avviso non è stato aggiornato. Riprova.')
    } finally {
      setBusy(null)
    }
  }

  const dismiss = async (alert: Alert) => {
    setBusy(alert.id)
    setError('')
    try {
      await api.fetch(`/api/v1/alerts/${alert.id}/dismiss`, { method: 'PATCH' })
      setAlerts((prev) => prev.filter((a) => a.id !== alert.id))
      setSummary((prev) =>
        prev
          ? { total: Math.max(0, prev.total - 1), unread: Math.max(0, prev.unread - (alert.is_read ? 0 : 1)) }
          : prev,
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : 'L’avviso non è stato archiviato. Riprova.')
    } finally {
      setBusy(null)
    }
  }

  const visible = useMemo(
    () =>
      alerts.filter((a) => {
        if (severity && a.severity !== severity) return false
        if (readState === 'unread' && a.is_read) return false
        if (readState === 'read' && !a.is_read) return false
        return true
      }),
    [alerts, severity, readState],
  )

  const filtered = severity !== '' || readState !== 'all'

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end gap-4">
        <Field label="Gravità" htmlFor="alerts-severity" className="w-full sm:w-52">
          <Select id="alerts-severity" value={severity} onChange={(e) => setSeverity(e.target.value as Severity | '')}>
            <option value="">Tutte</option>
            {SEVERITIES.map((s) => (
              <option key={s} value={s}>
                {SEVERITY_META[s].label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Stato" htmlFor="alerts-read" className="w-full sm:w-52">
          <Select id="alerts-read" value={readState} onChange={(e) => setReadState(e.target.value as 'all' | 'unread' | 'read')}>
            <option value="all">Tutti</option>
            <option value="unread">Non letti</option>
            <option value="read">Letti</option>
          </Select>
        </Field>
        {summary && (
          <p className="text-small text-ink-2 sm:ml-auto">
            {summary.total} {summary.total === 1 ? 'avviso' : 'avvisi'}, {summary.unread} non{' '}
            {summary.unread === 1 ? 'letto' : 'letti'}
          </p>
        )}
      </div>

      {error && (
        <p className="rounded-md border border-bad/30 bg-bad/5 px-4 py-3 text-small text-bad" role="alert">
          {error}
        </p>
      )}

      {loading ? (
        <div className="rounded-lg border border-rule bg-surface px-5 py-4">
          <SkeletonText lines={3} />
        </div>
      ) : visible.length === 0 ? (
        <EmptyState
          title={filtered ? 'Nessun avviso con questi filtri' : 'Nessun avviso per la vostra organizzazione'}
          description={
            filtered
              ? 'Cambia gravità o stato per vedere gli altri avvisi.'
              : 'Gli avvisi vengono creati dalle analisi e dal monitoraggio dei clienti; quando ci saranno, compariranno qui.'
          }
          action={
            filtered ? (
              <Button
                type="button"
                variant="secondary"
                onClick={() => {
                  setSeverity('')
                  setReadState('all')
                }}
              >
                Togli i filtri
              </Button>
            ) : undefined
          }
        />
      ) : (
        <div className="space-y-3">
          {visible.map((a) => (
            <AlertCard
              key={a.id}
              alert={a}
              today={today}
              busy={busy === a.id}
              onRead={() => markRead(a)}
              onDismiss={() => dismiss(a)}
            />
          ))}
        </div>
      )}

      <p className="text-caption text-ink-3">
        Gli avvisi sono generati da un sistema di IA (Regolamento (UE) 2024/1689, art. 50). Verifica sul testo ufficiale
        prima di decisioni vincolanti.
      </p>
    </div>
  )
}
