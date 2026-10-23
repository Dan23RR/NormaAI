'use client'

import { useCallback, useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { Badge, Button, Skeleton, StatCard, TBody, TD, TH, THead, TR, Table, type BadgeTone } from '@/components/ui'
import { api } from '@/lib/api'
import { formatInt, formatIsoDateTime } from '@/components/clienti/format'

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

const STATUS_META: Record<string, { label: string; tone: BadgeTone }> = {
  healthy: { label: 'Operativo', tone: 'ok' },
  degraded: { label: 'Degradato', tone: 'warn' },
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 py-3 sm:grid-cols-[200px_1fr] sm:gap-6">
      <dt className="text-small text-ink-2">{label}</dt>
      <dd className="text-body text-ink">{children}</dd>
    </div>
  )
}

function formatMs(value: number | undefined): string {
  if (typeof value !== 'number') return 'n.d.'
  return `${formatInt(Math.round(value))} ms`
}

export function SystemStatusSection() {
  const [state, setState] = useState<State>({ status: 'loading' })

  const load = useCallback(async () => {
    setState((prev) => (prev.status === 'ready' ? prev : { status: 'loading' }))
    try {
      const stats = await api.get<StatsResponse>('/api/v1/stats')
      setState({ status: 'ready', stats, at: new Date().toISOString() })
    } catch (err) {
      setState({ status: 'error', message: err instanceof Error ? err.message : 'Caricamento non riuscito.' })
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  if (state.status === 'loading') {
    return (
      <div className="space-y-3" role="status" aria-label="Caricamento dello stato del sistema">
        <Skeleton className="h-6 w-40" label="Caricamento dello stato del sistema" />
        <Skeleton className="h-48" label="Caricamento dello stato del sistema" />
      </div>
    )
  }

  if (state.status === 'error') {
    return (
      <div role="alert" className="rounded-lg border border-bad/30 bg-surface p-5">
        <h3 className="text-h4">Lo stato del sistema non si è caricato</h3>
        <p className="mt-1 text-body text-ink-2">{state.message}</p>
        <Button variant="secondary" className="mt-4" onClick={load}>
          Riprova il caricamento
        </Button>
      </div>
    )
  }

  const { stats } = state
  const status = stats.status ? (STATUS_META[stats.status] ?? { label: stats.status, tone: 'neutral' as BadgeTone }) : null
  const endpoints = Object.entries(stats.metrics?.endpoints ?? {}).sort(([, a], [, b]) => (b.count ?? 0) - (a.count ?? 0))
  const hasP95 = endpoints.some(([, m]) => typeof m.p95_latency_ms === 'number' && m.p95_latency_ms > 0)
  const total = stats.metrics?.total_requests

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          {status && <Badge tone={status.tone}>{status.label}</Badge>}
          <p className="text-small text-ink-2">
            Letto dal server il <span className="tabular">{formatIsoDateTime(stats.timestamp) ?? formatIsoDateTime(state.at)}</span>
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={load} iconLeft={<RefreshCw className="h-4 w-4" aria-hidden="true" />}>
          Aggiorna lo stato
        </Button>
      </div>

      <dl className="divide-y divide-rule rounded-lg border border-rule bg-surface px-5">
        {stats.version && <Row label="Versione">{stats.version}</Row>}
        {stats.environment && <Row label="Ambiente">{stats.environment}</Row>}
        {stats.llm_provider && <Row label="Provider LLM">{stats.llm_provider}</Row>}
        {stats.llm_model && <Row label="Modello">{stats.llm_model}</Row>}
        {typeof stats.llm_available === 'boolean' && (
          <Row label="LLM">
            <Badge tone={stats.llm_available ? 'ok' : 'bad'}>{stats.llm_available ? 'Configurato' : 'Chiave mancante'}</Badge>
          </Row>
        )}
        {typeof stats.qdrant_available === 'boolean' && (
          <Row label="Qdrant (base vettoriale)">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={stats.qdrant_available ? 'ok' : 'bad'}>
                {stats.qdrant_available ? 'Disponibile' : 'Non disponibile'}
              </Badge>
              {stats.qdrant?.status && stats.qdrant.status !== (stats.qdrant_available ? 'ok' : 'unavailable') && (
                <span className="text-small text-ink-2">stato: {stats.qdrant.status}</span>
              )}
              {typeof stats.qdrant?.points_count === 'number' && (
                <span className="text-small text-ink-2 tabular">{formatInt(stats.qdrant.points_count)} blocchi indicizzati</span>
              )}
            </div>
          </Row>
        )}
      </dl>

      {stats.metrics ? (
        <section aria-labelledby="metrics-title" className="space-y-4">
          <h3 id="metrics-title" className="text-h4">
            Richieste dall’avvio del server
          </h3>
          <div className="grid gap-3 sm:grid-cols-2">
            <StatCard label="Richieste totali" value={formatInt(total) ?? 'n.d.'} />
            <StatCard
              label="Errori"
              value={formatInt(stats.metrics.error_count) ?? 'n.d.'}
              tone={typeof stats.metrics.error_count === 'number' && stats.metrics.error_count > 0 ? 'bad' : undefined}
            />
          </div>
          {endpoints.length === 0 ? (
            <p className="text-small text-ink-2">Nessuna richiesta registrata da quando il server è partito.</p>
          ) : (
            <Table>
              <THead>
                <TR>
                  <TH>Endpoint</TH>
                  <TH numeric>Richieste</TH>
                  <TH numeric className="hidden sm:table-cell">
                    Quota
                  </TH>
                  <TH numeric>Latenza media</TH>
                  <TH numeric className="hidden md:table-cell">
                    Massima
                  </TH>
                  {hasP95 && (
                    <TH numeric className="hidden md:table-cell">
                      p95
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
                    <TD numeric>{formatInt(m.count) ?? 'n.d.'}</TD>
                    <TD numeric className="hidden text-ink-2 sm:table-cell">
                      {typeof total === 'number' && total > 0 && typeof m.count === 'number'
                        ? `${((m.count / total) * 100).toFixed(1).replace('.', ',')}%`
                        : 'n.d.'}
                    </TD>
                    <TD numeric className="whitespace-nowrap text-ink-2">
                      {formatMs(m.avg_latency_ms)}
                    </TD>
                    <TD numeric className="hidden whitespace-nowrap text-ink-2 md:table-cell">
                      {formatMs(m.max_latency_ms)}
                    </TD>
                    {hasP95 && (
                      <TD numeric className="hidden whitespace-nowrap text-ink-2 md:table-cell">
                        {m.p95_latency_ms ? formatMs(m.p95_latency_ms) : 'n.d.'}
                      </TD>
                    )}
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </section>
      ) : (
        <p className="text-small text-ink-2">
          Il server non ha incluso i contatori delle richieste nella risposta: li mostra solo a una sessione da
          amministratore.
        </p>
      )}
    </div>
  )
}
