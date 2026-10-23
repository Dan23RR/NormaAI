'use client'

import { useEffect, useState, type FormEvent } from 'react'
import { FileDown, FileText } from 'lucide-react'
import { Badge, Button, ButtonLink, Checkbox, Field, Select, frameworkLabel } from '@/components/ui'
import type { Client, GapAnalysisResponse } from '@/lib/types'
import { FRAMEWORK_KEYS, isFrameworkKey, type FrameworkKey } from '@/components/clienti/clients-api'
import { clientToProfile } from '@/components/clienti/ComplianceTab'
import { STATUS_SUMMARY_KEYS, complianceAssessment, confidenceAssessment, statusMeta } from '@/components/clienti/compliance'
import { formatIsoDateTime } from '@/components/clienti/format'
import {
  REPORT_TYPE_LABEL,
  downloadBlob,
  generatePdf,
  runDemoAnalyses,
  saveDemoReport,
  type ReportHistoryItem,
  type ReportType,
} from './report-api'

export interface ReportPrefill {
  clientId: string | null
  type: ReportType
  frameworks: string[]
}

type Outcome =
  | { kind: 'pdf'; filename: string; at: string }
  | { kind: 'demo'; analyses: GapAnalysisResponse[]; at: string }

function knownFrameworks(client: Client | undefined): FrameworkKey[] {
  return (client?.applicable_frameworks ?? []).filter(isFrameworkKey)
}

/**
 * The generation form. With a real account the backend streams the PDF
 * back and the browser downloads it; in the demo the analysis runs on
 * sample data and the content is shown on screen.
 */
export function ReportGenerator({
  clients,
  demoMode,
  prefill,
  onGenerated,
}: {
  clients: Client[]
  demoMode: boolean
  prefill: ReportPrefill | null
  onGenerated: (item: ReportHistoryItem) => void
}) {
  const [clientId, setClientId] = useState<string>('')
  const [type, setType] = useState<ReportType>('gap_analysis')
  const [framework, setFramework] = useState<FrameworkKey>('CSRD')
  const [frameworks, setFrameworks] = useState<FrameworkKey[]>(['CSRD'])
  const [formError, setFormError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [outcome, setOutcome] = useState<Outcome | null>(null)

  const client = clients.find((c) => c.id === clientId)

  // First client as the default once the list arrives.
  useEffect(() => {
    if (!clientId && clients.length > 0) selectClient(clients[0].id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clients])

  useEffect(() => {
    if (!prefill) return
    if (prefill.clientId) setClientId(prefill.clientId)
    setType(prefill.type)
    const known = prefill.frameworks.filter(isFrameworkKey)
    if (prefill.type === 'gap_analysis' && known[0]) setFramework(known[0])
    if (prefill.type === 'executive_summary' && known.length > 0) setFrameworks(known)
    setOutcome(null)
    setError(null)
    document.getElementById('report-client')?.focus()
  }, [prefill])

  const selectClient = (id: string) => {
    setClientId(id)
    const known = knownFrameworks(clients.find((c) => c.id === id))
    if (known.length > 0) {
      setFramework(known[0])
      setFrameworks(known)
    }
  }

  const toggleFramework = (key: FrameworkKey) => {
    setFrameworks((prev) => (prev.includes(key) ? prev.filter((f) => f !== key) : [...prev, key]))
    setFormError(null)
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!client) {
      setFormError('Scegli il cliente per cui generare il report.')
      return
    }
    const selected = type === 'gap_analysis' ? [framework] : frameworks
    if (selected.length === 0) {
      setFormError('Seleziona almeno un framework per la sintesi.')
      return
    }
    setFormError(null)
    setError(null)
    setOutcome(null)
    setLoading(true)
    const profile = clientToProfile(client)
    const at = new Date().toISOString()
    try {
      if (demoMode) {
        const analyses = await runDemoAnalyses(selected, profile)
        const avg = analyses.reduce((sum, a) => sum + (a.overall_score ?? 0), 0) / analyses.length
        const item: ReportHistoryItem = {
          id: `demo-${Date.now()}`,
          report_type: type,
          framework: type === 'gap_analysis' ? selected[0] : null,
          frameworks: type === 'executive_summary' ? selected : null,
          company_name: client.name,
          generated_at: at,
          overall_score: avg,
        }
        saveDemoReport(item)
        setOutcome({ kind: 'demo', analyses, at })
        onGenerated(item)
      } else {
        const { blob, filename } = await generatePdf(type, selected, profile)
        downloadBlob(blob, filename)
        setOutcome({ kind: 'pdf', filename, at })
        onGenerated({
          id: `local-${Date.now()}`,
          report_type: type,
          framework: type === 'gap_analysis' ? selected[0] : null,
          frameworks: type === 'executive_summary' ? selected : null,
          company_name: client.name,
          generated_at: at,
          overall_score: null,
        })
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Generazione non riuscita. Riprova.')
    } finally {
      setLoading(false)
    }
  }

  if (clients.length === 0) {
    return (
      <div className="rounded-lg border border-rule bg-surface p-5">
        <h3 className="text-h4">Serve prima un cliente</h3>
        <p className="mt-1 max-w-prose text-body text-ink-2">
          Il report parte dal profilo di un cliente: nome, settore, dimensione e framework seguiti.
        </p>
        <ButtonLink href="/app/clienti" className="mt-4">
          Crea il primo cliente
        </ButtonLink>
      </div>
    )
  }

  const selectedLabel = (type === 'gap_analysis' ? [framework] : frameworks).map(frameworkLabel).join(', ')

  return (
    <div className="space-y-6">
      <form onSubmit={submit} noValidate className="rounded-lg border border-rule bg-surface p-5">
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Cliente" htmlFor="report-client" required>
            <Select id="report-client" value={clientId} onChange={(e) => selectClient(e.target.value)} disabled={loading}>
              {clients.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field
            label="Tipo di report"
            htmlFor="report-type"
            help={
              type === 'gap_analysis'
                ? 'Un framework: requisiti, stato, gap e raccomandazioni.'
                : 'Più framework in un quadro unico per la direzione.'
            }
          >
            <Select
              id="report-type"
              value={type}
              onChange={(e) => setType(e.target.value as ReportType)}
              disabled={loading}
              aria-describedby="report-type-help"
            >
              {(Object.keys(REPORT_TYPE_LABEL) as ReportType[]).map((key) => (
                <option key={key} value={key}>
                  {REPORT_TYPE_LABEL[key]}
                </option>
              ))}
            </Select>
          </Field>
          {type === 'gap_analysis' ? (
            <Field label="Framework" htmlFor="report-framework" required>
              <Select
                id="report-framework"
                value={framework}
                onChange={(e) => setFramework(e.target.value as FrameworkKey)}
                disabled={loading}
              >
                {FRAMEWORK_KEYS.map((key) => (
                  <option key={key} value={key}>
                    {frameworkLabel(key)}
                  </option>
                ))}
              </Select>
            </Field>
          ) : (
            <fieldset className="md:col-span-2">
              <legend className="text-small font-medium text-ink">Framework da includere</legend>
              <div className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                {FRAMEWORK_KEYS.map((key) => (
                  <Checkbox
                    key={key}
                    id={`report-fw-${key}`}
                    label={frameworkLabel(key)}
                    checked={frameworks.includes(key)}
                    onChange={() => toggleFramework(key)}
                    disabled={loading}
                  />
                ))}
              </div>
            </fieldset>
          )}
        </div>

        {formError && (
          <p role="alert" className="mt-4 text-small text-bad">
            {formError}
          </p>
        )}

        <div className="mt-5 flex flex-wrap items-center gap-3">
          <Button
            type="submit"
            loading={loading}
            iconLeft={demoMode ? <FileText className="h-4 w-4" aria-hidden="true" /> : <FileDown className="h-4 w-4" aria-hidden="true" />}
          >
            {loading ? 'Generazione in corso' : demoMode ? 'Genera l’anteprima del report' : 'Genera e scarica il PDF'}
          </Button>
          {demoMode && !loading && (
            <p className="text-caption text-ink-3">Nella demo il PDF non viene prodotto: il contenuto compare qui sotto.</p>
          )}
        </div>
      </form>

      {loading && client && (
        <p role="status" className="rounded-md border border-rule bg-surface-2 px-4 py-3 text-small text-ink-2">
          Analisi di {client.name} per {selectedLabel}. Fino a un minuto per ogni framework.
        </p>
      )}

      {error && (
        <div role="alert" className="rounded-lg border border-bad/30 bg-surface p-5">
          <h3 className="text-h4">Il report non è stato generato</h3>
          <p className="mt-1 text-body text-ink-2">{error}</p>
        </div>
      )}

      {outcome?.kind === 'pdf' && (
        <div role="status" className="rounded-lg border border-ok/30 bg-surface p-5">
          <h3 className="text-h4">PDF scaricato</h3>
          <p className="mt-1 text-body text-ink-2">
            <span className="font-medium text-ink">{outcome.filename}</span>, generato il{' '}
            <span className="tabular">{formatIsoDateTime(outcome.at)}</span>. Lo trovi nella cartella dei download del
            browser: conservalo, perché il server non permette ancora di riscaricarlo.
          </p>
        </div>
      )}

      {outcome?.kind === 'demo' && client && (
        <section aria-labelledby="report-preview-title" className="space-y-4">
          <div>
            <h3 id="report-preview-title" className="text-h3">
              Anteprima del report per {client.name}
            </h3>
            <p className="mt-1 text-caption text-ink-3 tabular">
              Demo con dati di esempio, generata il {formatIsoDateTime(outcome.at)}
            </p>
          </div>
          {outcome.analyses.map((analysis, i) => {
            const overall = complianceAssessment(analysis.overall_score ?? 0)
            const confidence = confidenceAssessment(analysis.confidence_score ?? 0)
            const summary = (analysis.status_summary ?? {}) as Record<string, number | undefined>
            return (
              <article key={`${analysis.framework}-${i}`} className="rounded-lg border border-rule bg-surface p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <h4 className="text-h4">{frameworkLabel(analysis.framework)}</h4>
                  <div className="flex flex-wrap gap-2">
                    <Badge tone={overall.tone} title={overall.sublabel}>
                      {overall.label}
                    </Badge>
                    <Badge tone={confidence.tone} title={confidence.sublabel}>
                      {confidence.label}
                    </Badge>
                  </div>
                </div>
                <dl className="mt-3 flex flex-wrap gap-x-5 gap-y-2">
                  {STATUS_SUMMARY_KEYS.map(({ key, status }) => {
                    const count = summary[key]
                    if (typeof count !== 'number') return null
                    const meta = statusMeta(status)
                    return (
                      <div key={key} className="flex items-center gap-2">
                        <dt>
                          <Badge tone={meta.tone}>{meta.label}</Badge>
                        </dt>
                        <dd className="text-body font-medium tabular">{count}</dd>
                      </div>
                    )
                  })}
                </dl>
                {analysis.top_recommendations?.length > 0 && (
                  <ol className="mt-4 max-w-prose list-decimal space-y-1 pl-5 text-body text-ink">
                    {analysis.top_recommendations.slice(0, 3).map((rec, j) => (
                      <li key={j}>{rec}</li>
                    ))}
                  </ol>
                )}
              </article>
            )
          })}
          <p className="max-w-prose text-caption text-ink-3">
            Analisi generata da un sistema di IA (Regolamento (UE) 2024/1689, art. 50): stima preliminare, non una
            certificazione né una consulenza legale.
          </p>
        </section>
      )}
    </div>
  )
}
