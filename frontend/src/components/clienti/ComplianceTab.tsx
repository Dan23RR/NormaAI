'use client'

import { useEffect, useState, type FormEvent } from 'react'
import { ClipboardCheck } from 'lucide-react'
import { Badge, Button, EmptyState, Field, Select, TBody, TD, TH, THead, TR, Table, frameworkLabel } from '@/components/ui'
import { api } from '@/lib/api'
import type { ApiResponse, Client, CompanyProfile, GapAnalysisResponse, Requirement } from '@/lib/types'
import { FRAMEWORK_KEYS, isFrameworkKey, type FrameworkKey } from './clients-api'
import {
  PRIORITY_TONE,
  STATUS_SUMMARY_KEYS,
  complianceAssessment,
  confidenceAssessment,
  effortLabel,
  statusMeta,
} from './compliance'
import { formatIsoDateTime } from './format'

interface StoredAnalysis {
  framework: FrameworkKey
  result: GapAnalysisResponse
  analysedAt: string
}

const storageKey = (clientId: string) => `normaai_client_gap_${clientId}`

function loadStored(clientId: string): StoredAnalysis | null {
  try {
    const raw = sessionStorage.getItem(storageKey(clientId))
    return raw ? (JSON.parse(raw) as StoredAnalysis) : null
  } catch {
    return null
  }
}

function store(clientId: string, value: StoredAnalysis) {
  try {
    sessionStorage.setItem(storageKey(clientId), JSON.stringify(value))
  } catch {
    /* the result stays on screen for this visit only */
  }
}

/** The profile the analysis endpoint expects, built from the client record. */
export function clientToProfile(client: Client): CompanyProfile {
  return {
    name: client.name,
    sector: client.sector ?? '',
    employee_count: typeof client.employee_count === 'number' ? client.employee_count : 0,
    revenue_eur: typeof client.revenue_eur === 'number' ? client.revenue_eur : 0,
    jurisdictions: client.jurisdictions ?? [],
    applicable_frameworks: client.applicable_frameworks ?? [],
    existing_documents: '',
  }
}

function defaultFramework(client: Client): FrameworkKey {
  const first = (client.applicable_frameworks ?? []).find(isFrameworkKey)
  return first ?? 'CSRD'
}

/**
 * Gap analysis for one client and one framework. The overall result is a
 * qualitative label (never the numeric score), each requirement a row with
 * its status, gap, effort and priority.
 */
export function ComplianceTab({ client }: { client: Client }) {
  const [framework, setFramework] = useState<FrameworkKey>(() => defaultFramework(client))
  const [analysis, setAnalysis] = useState<StoredAnalysis | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const stored = loadStored(client.id)
    if (stored) {
      setAnalysis(stored)
      setFramework(stored.framework)
    }
  }, [client.id])

  const run = async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const res = await api.post<ApiResponse<GapAnalysisResponse>>('/api/v1/gap-analysis', {
        framework,
        company_profile: clientToProfile(client),
      })
      const next: StoredAnalysis = { framework, result: res.data, analysedAt: new Date().toISOString() }
      setAnalysis(next)
      store(client.id, next)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analisi non riuscita. Riprova.')
    } finally {
      setLoading(false)
    }
  }

  const result = analysis?.result
  const overall = result ? complianceAssessment(result.overall_score ?? 0) : null
  const confidence = result ? confidenceAssessment(result.confidence_score ?? 0) : null
  const requirements: Requirement[] = result?.requirements ?? []
  const summary = (result?.status_summary ?? {}) as Record<string, number | undefined>

  return (
    <div className="space-y-6">
      <form onSubmit={run} className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <Field label="Framework" htmlFor="gap-framework" className="w-full sm:max-w-xs">
          <Select
            id="gap-framework"
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
        <Button type="submit" loading={loading} iconLeft={<ClipboardCheck className="h-4 w-4" aria-hidden="true" />}>
          {loading ? 'Analisi in corso' : analysis ? 'Ripeti l’analisi' : 'Avvia l’analisi'}
        </Button>
      </form>

      {loading && (
        <p role="status" className="rounded-md border border-rule bg-surface-2 px-4 py-3 text-small text-ink-2">
          Confronto del profilo di {client.name} con i requisiti {frameworkLabel(framework)}. Può richiedere fino a un
          minuto.
        </p>
      )}

      {error && (
        <div role="alert" className="rounded-lg border border-bad/30 bg-surface p-5">
          <h3 className="text-h4">L’analisi non è riuscita</h3>
          <p className="mt-1 text-body text-ink-2">{error}</p>
        </div>
      )}

      {!loading && !result && !error && (
        <EmptyState
          icon={<ClipboardCheck className="h-8 w-8" aria-hidden="true" />}
          title="Nessuna analisi per questo cliente"
          description="Scegli un framework e avvia l’analisi: il profilo viene confrontato con i requisiti dell’atto, articolo per articolo."
        />
      )}

      {result && overall && confidence && analysis && (
        <div className="space-y-6">
          <section className="rounded-lg border border-rule bg-surface p-5" aria-labelledby="gap-result-title">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 id="gap-result-title" className="text-h3">
                  Valutazione {frameworkLabel(analysis.framework)}
                </h3>
                <p className="mt-1 text-caption text-ink-3 tabular">
                  Analisi del {formatIsoDateTime(analysis.analysedAt)}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge tone={overall.tone} title={overall.sublabel}>
                  {overall.label}
                </Badge>
                <Badge tone={confidence.tone} title={confidence.sublabel}>
                  {confidence.label}
                </Badge>
                {result.requires_expert_review && <Badge tone="warn">Revisione di un esperto consigliata</Badge>}
              </div>
            </div>
            <p className="mt-3 max-w-prose text-body text-ink-2">{overall.sublabel}.</p>

            <dl className="mt-4 flex flex-wrap gap-x-6 gap-y-2">
              {STATUS_SUMMARY_KEYS.map(({ key, status }) => {
                const count = summary[key]
                if (typeof count !== 'number') return null
                const meta = statusMeta(status)
                return (
                  <div key={key} className="flex items-center gap-2">
                    <dt>
                      <Badge tone={meta.tone}>{meta.label}</Badge>
                    </dt>
                    <dd className="text-body font-medium tabular text-ink">{count}</dd>
                  </div>
                )
              })}
            </dl>

            <p className="mt-4 max-w-prose text-caption text-ink-3">
              Analisi generata da un sistema di IA (Regolamento (UE) 2024/1689, art. 50): è una stima preliminare basata
              sul profilo inserito, non una certificazione di conformità né una consulenza legale.
            </p>
          </section>

          {requirements.length > 0 && (
            <section aria-labelledby="gap-requirements-title">
              <h3 id="gap-requirements-title" className="mb-3 text-h4">
                Requisiti ({requirements.length})
              </h3>
              <Table>
                <THead>
                  <TR>
                    <TH>Requisito</TH>
                    <TH>Stato</TH>
                    <TH className="hidden md:table-cell">Gap</TH>
                    <TH className="hidden sm:table-cell">Impegno</TH>
                    <TH>Priorità</TH>
                  </TR>
                </THead>
                <TBody>
                  {requirements.map((req, i) => {
                    const status = statusMeta(req.status)
                    const effort = effortLabel(req.remediation_effort)
                    return (
                      <TR key={req.requirement_id || i}>
                        <TD>
                          <p className="text-body text-ink">{req.description}</p>
                          {req.article_reference && (
                            <p className="mt-0.5 text-caption text-ink-3">{req.article_reference}</p>
                          )}
                          {req.gap_description && (
                            <p className="mt-1 text-small text-ink-2 md:hidden">{req.gap_description}</p>
                          )}
                        </TD>
                        <TD>
                          <Badge tone={status.tone}>{status.label}</Badge>
                        </TD>
                        <TD className="hidden max-w-md text-small text-ink-2 md:table-cell">
                          {req.gap_description || <span className="text-ink-3">Nessun gap rilevato</span>}
                        </TD>
                        <TD className="hidden text-small text-ink-2 sm:table-cell">{effort}</TD>
                        <TD>
                          {req.priority ? (
                            <Badge tone={PRIORITY_TONE[req.priority] ?? 'neutral'}>{req.priority}</Badge>
                          ) : (
                            <span className="text-ink-3">n.d.</span>
                          )}
                        </TD>
                      </TR>
                    )
                  })}
                </TBody>
              </Table>
            </section>
          )}

          {result.top_recommendations?.length > 0 && (
            <section aria-labelledby="gap-recommendations-title" className="rounded-lg border border-rule bg-surface p-5">
              <h3 id="gap-recommendations-title" className="text-h4">
                Raccomandazioni principali
              </h3>
              <ol className="mt-3 max-w-prose list-decimal space-y-2 pl-5 text-body text-ink">
                {result.top_recommendations.map((rec, i) => (
                  <li key={i}>{rec}</li>
                ))}
              </ol>
            </section>
          )}
        </div>
      )}
    </div>
  )
}
