'use client'

import { useCallback, useEffect, useState } from 'react'
import { useFormatter, useTranslations } from 'next-intl'
import { RefreshCw } from 'lucide-react'
import { Badge, Button, Skeleton, StatCard, TBody, TD, TH, THead, TR, Table, type BadgeTone } from '@/components/ui'
import { useErrorText } from '@/i18n/errors'
import { INT } from '@/i18n/format'
import { api } from '@/lib/api'
import { formatIsoDateTime } from '@/components/clienti/format'

/**
 * What GET /api/v1/stats returns (src/api/routers/system.py). Everything
 * past the first five keys is present only for admins; the Qdrant block
 * and the metrics depend on what the server could measure.
 */
interface StatsResponse {
  status?: string
  version?: string
  timestamp?: string
  qdrant_available?: boolean
  llm_available?: boolean
  environment?: string
  llm_provider?: string
  llm_model?: string
  qdrant?: { status?: string; points_count?: number; [key: string]: unknown }
  metrics?: {
    total_requests?: number
    error_count?: number
    endpoints?: Record<string, { count?: number; avg_latency_ms?: number; max_latency_ms?: number; p95_latency_ms?: number }>
  }
}

type State = { status: 'loading' } | { status: 'error'; message: string } | { status: 'ready'; stats: StatsResponse; at: string }

const STATUS_TONE: Record<string, BadgeTone> = {
  healthy: 'ok',
  degraded: 'warn',
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 py-3 sm:grid-cols-[200px_1fr] sm:gap-6">
      <dt className="text-small text-ink-2">{label}</dt>
      <dd className="text-body text-ink">{children}</dd>
    </div>
  )
}

export function SystemStatusSection() {
  const t = useTranslations('admin.system')
  const tu = useTranslations('ui')
  const format = useFormatter()
  const errorText = useErrorText()
  const [state, setState] = useState<State>({ status: 'loading' })

  const load = useCallback(async () => {
    setState((prev) => (prev.status === 'ready' ? prev : { status: 'loading' }))
    try {
      const stats = await api.get<StatsResponse>('/api/v1/stats')
      setState({ status: 'ready', stats, at: new Date().toISOString() })
    } catch (err) {
      setState({ status: 'error', message: errorText(err, 'errors.loadFailed') })
    }
  }, [errorText])

  useEffect(() => {
    load()
  }, [load])

  const missing = tu('notAvailable')
  const int = (value: number | undefined) => (typeof value === 'number' ? format.number(value, INT) : missing)
  const formatMs = (value: number | undefined) =>
    typeof value === 'number' ? t('ms', { value: format.number(Math.round(value), INT) }) : missing

  if (state.status === 'loading') {
    return (
      <div className="space-y-3" role="status" aria-label={t('loading')}>
        <Skeleton className="h-6 w-40" label={t('loading')} />
        <Skeleton className="h-48" label={t('loading')} />
      </div>
    )
  }

  if (state.status === 'error') {
    return (
      <div role="alert" className="rounded-lg border border-bad/30 bg-surface p-5">
        <h3 className="text-h4">{t('loadFailedTitle')}</h3>
        <p className="mt-1 text-body text-ink-2">{state.message}</p>
        <Button variant="secondary" className="mt-4" onClick={load}>
          {tu('retryLoad')}
        </Button>
      </div>
    )
  }

  const { stats } = state
  const status = stats.status
    ? { label: stats.status in STATUS_TONE ? t(`status.${stats.status}`) : stats.status, tone: STATUS_TONE[stats.status] ?? ('neutral' as BadgeTone) }
    : null
  const endpoints = Object.entries(stats.metrics?.endpoints ?? {}).sort(([, a], [, b]) => (b.count ?? 0) - (a.count ?? 0))
  const hasP95 = endpoints.some(([, m]) => typeof m.p95_latency_ms === 'number' && m.p95_latency_ms > 0)
  const total = stats.metrics?.total_requests

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          {status && <Badge tone={status.tone}>{status.label}</Badge>}
          <p className="text-small text-ink-2">
            {t.rich('readAt', {
              date: formatIsoDateTime(stats.timestamp) ?? formatIsoDateTime(state.at) ?? missing,
              num: (chunks) => <span className="tabular">{chunks}</span>,
            })}
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={load} iconLeft={<RefreshCw className="h-4 w-4" aria-hidden="true" />}>
          {t('refresh')}
        </Button>
      </div>

      <dl className="divide-y divide-rule rounded-lg border border-rule bg-surface px-5">
        {stats.version && <Row label={t('version')}>{stats.version}</Row>}
        {stats.environment && <Row label={t('environment')}>{stats.environment}</Row>}
        {stats.llm_provider && <Row label={t('provider')}>{stats.llm_provider}</Row>}
        {stats.llm_model && <Row label={t('model')}>{stats.llm_model}</Row>}
        {typeof stats.llm_available === 'boolean' && (
          <Row label={t('llm')}>
            <Badge tone={stats.llm_available ? 'ok' : 'bad'}>{stats.llm_available ? t('llmOk') : t('llmMissing')}</Badge>
          </Row>
        )}
        {typeof stats.qdrant_available === 'boolean' && (
          <Row label={t('qdrant')}>
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={stats.qdrant_available ? 'ok' : 'bad'}>
                {stats.qdrant_available ? t('available') : t('unavailable')}
              </Badge>
              {stats.qdrant?.status && stats.qdrant.status !== (stats.qdrant_available ? 'ok' : 'unavailable') && (
                <span className="text-small text-ink-2">{t('qdrantStatus', { status: stats.qdrant.status })}</span>
              )}
              {typeof stats.qdrant?.points_count === 'number' && (
                <span className="text-small text-ink-2 tabular">{t('chunks', { count: format.number(stats.qdrant.points_count, INT) })}</span>
              )}
            </div>
          </Row>
        )}
      </dl>

      {stats.metrics ? (
        <section aria-labelledby="metrics-title" className="space-y-4">
          <h3 id="metrics-title" className="text-h4">
            {t('requestsTitle')}
          </h3>
          <div className="grid gap-3 sm:grid-cols-2">
            <StatCard label={t('totalRequests')} value={int(total)} />
            <StatCard
              label={t('errors')}
              value={int(stats.metrics.error_count)}
              tone={typeof stats.metrics.error_count === 'number' && stats.metrics.error_count > 0 ? 'bad' : undefined}
            />
          </div>
          {endpoints.length === 0 ? (
            <p className="text-small text-ink-2">{t('noRequests')}</p>
          ) : (
            <Table>
              <THead>
                <TR>
                  <TH>{t('colEndpoint')}</TH>
                  <TH numeric>{t('colRequests')}</TH>
                  <TH numeric className="hidden sm:table-cell">
                    {t('colShare')}
                  </TH>
                  <TH numeric>{t('colAvg')}</TH>
                  <TH numeric className="hidden md:table-cell">
                    {t('colMax')}
                  </TH>
                  {hasP95 && (
                    <TH numeric className="hidden md:table-cell">
                      {t('colP95')}
                    </TH>
                  )}
                </TR>
              </THead>
              <TBody>
                {endpoints.map(([endpoint, m]) => (
                  <TR key={endpoint}>
                    <TD>
                      <code className="font-mono text-small text-ink">{endpoint}</code>
                    </TD>
                    <TD numeric>{int(m.count)}</TD>
                    <TD numeric className="hidden text-ink-2 sm:table-cell">
                      {typeof total === 'number' && total > 0 && typeof m.count === 'number'
                        ? format.number(m.count / total, { style: 'percent', maximumFractionDigits: 1 })
                        : missing}
                    </TD>
                    <TD numeric className="whitespace-nowrap text-ink-2">
                      {formatMs(m.avg_latency_ms)}
                    </TD>
                    <TD numeric className="hidden whitespace-nowrap text-ink-2 md:table-cell">
                      {formatMs(m.max_latency_ms)}
                    </TD>
                    {hasP95 && (
                      <TD numeric className="hidden whitespace-nowrap text-ink-2 md:table-cell">
                        {m.p95_latency_ms ? formatMs(m.p95_latency_ms) : missing}
                      </TD>
                    )}
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </section>
      ) : (
        <p className="text-small text-ink-2">{t('noMetrics')}</p>
      )}
    </div>
  )
}
