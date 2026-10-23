'use client'

import { useCallback, useEffect, useState } from 'react'
import { FileText } from 'lucide-react'
import { Button, EmptyState, PageHeader, Skeleton } from '@/components/ui'
import { useAuth } from '@/hooks/useAuth'
import type { Client } from '@/lib/types'
import { fetchClients } from '@/components/clienti/clients-api'
import { ReportGenerator, type ReportPrefill } from '@/components/report/ReportGenerator'
import { ReportHistoryTable } from '@/components/report/ReportHistoryTable'
import { fetchReportHistory, type ReportHistoryItem } from '@/components/report/report-api'

type Loadable<T> = { status: 'loading' } | { status: 'error'; message: string } | { status: 'ready'; data: T }

export default function ReportPage() {
  const { demoMode } = useAuth()
  const [clients, setClients] = useState<Loadable<Client[]>>({ status: 'loading' })
  const [history, setHistory] = useState<Loadable<ReportHistoryItem[]>>({ status: 'loading' })
  const [prefill, setPrefill] = useState<ReportPrefill | null>(null)

  const loadClients = useCallback(async () => {
    setClients({ status: 'loading' })
    try {
      setClients({ status: 'ready', data: await fetchClients() })
    } catch (err) {
      setClients({ status: 'error', message: err instanceof Error ? err.message : 'Caricamento non riuscito.' })
    }
  }, [])

  const loadHistory = useCallback(async () => {
    setHistory({ status: 'loading' })
    try {
      setHistory({ status: 'ready', data: await fetchReportHistory() })
    } catch (err) {
      setHistory({ status: 'error', message: err instanceof Error ? err.message : 'Caricamento non riuscito.' })
    }
  }, [])

  useEffect(() => {
    loadClients()
    loadHistory()
  }, [loadClients, loadHistory])

  const onGenerated = (item: ReportHistoryItem) => {
    if (demoMode) {
      setHistory((prev) => (prev.status === 'ready' ? { status: 'ready', data: [item, ...prev.data] } : prev))
    } else {
      loadHistory()
    }
  }

  const onRegenerate = (item: ReportHistoryItem) => {
    const list = clients.status === 'ready' ? clients.data : []
    const match = list.find((c) => c.name === item.company_name)
    setPrefill({
      clientId: match?.id ?? null,
      type: item.report_type === 'executive_summary' ? 'executive_summary' : 'gap_analysis',
      frameworks: item.frameworks ?? (item.framework ? [item.framework] : []),
    })
    document.getElementById('report-generate')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <div>
      <PageHeader
        title="Report"
        description="La gap analysis di un cliente su un framework, o una sintesi direzionale su più framework, in PDF."
      />

      <section id="report-generate" aria-labelledby="report-generate-title" className="scroll-mt-6">
        <h2 id="report-generate-title" className="mb-3 text-h3">
          Genera un report
        </h2>
        {clients.status === 'loading' && (
          <div className="space-y-3" role="status" aria-label="Caricamento dei clienti">
            <Skeleton className="h-10 w-full max-w-md" label="Caricamento dei clienti" />
            <Skeleton className="h-10 w-full max-w-md" label="Caricamento dei clienti" />
          </div>
        )}
        {clients.status === 'error' && (
          <div role="alert" className="rounded-lg border border-bad/30 bg-surface p-5">
            <h3 className="text-h4">I clienti non si sono caricati</h3>
            <p className="mt-1 text-body text-ink-2">{clients.message}</p>
            <Button variant="secondary" className="mt-4" onClick={loadClients}>
              Riprova il caricamento
            </Button>
          </div>
        )}
        {clients.status === 'ready' && (
          <ReportGenerator clients={clients.data} demoMode={demoMode} prefill={prefill} onGenerated={onGenerated} />
        )}
      </section>

      <section aria-labelledby="report-history-title" className="mt-10">
        <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
          <h2 id="report-history-title" className="text-h3">
            Report generati
          </h2>
          {history.status === 'ready' && history.data.length > 0 && (
            <p className="text-small text-ink-2">
              {history.data.length} {history.data.length === 1 ? 'report' : 'report'}
            </p>
          )}
        </div>
        <p className="mb-4 max-w-prose text-small text-ink-2">
          {demoMode
            ? 'Nella demo lo storico resta in questa sessione del browser.'
            : 'Il server conserva i dati di ogni report, non il PDF: il download dei PDF già generati è in ricostruzione. Per averne uno nuovo, usa «Genera di nuovo».'}
        </p>

        {history.status === 'loading' && (
          <div className="space-y-2" role="status" aria-label="Caricamento dei report">
            <Skeleton className="h-10" label="Caricamento dei report" />
            <Skeleton className="h-12" label="Caricamento dei report" />
            <Skeleton className="h-12" label="Caricamento dei report" />
          </div>
        )}
        {history.status === 'error' && (
          <div role="alert" className="rounded-lg border border-bad/30 bg-surface p-5">
            <h3 className="text-h4">Lo storico non si è caricato</h3>
            <p className="mt-1 text-body text-ink-2">{history.message}</p>
            <Button variant="secondary" className="mt-4" onClick={loadHistory}>
              Riprova il caricamento
            </Button>
          </div>
        )}
        {history.status === 'ready' && history.data.length === 0 && (
          <EmptyState
            icon={<FileText className="h-8 w-8" aria-hidden="true" />}
            title="Nessun report ancora"
            description="Il primo report compare qui appena lo generi dal modulo sopra."
          />
        )}
        {history.status === 'ready' && history.data.length > 0 && (
          <ReportHistoryTable items={history.data} onRegenerate={onRegenerate} />
        )}
      </section>
    </div>
  )
}
