'use client'

import { useEffect, useRef, useState } from 'react'
import { Badge, FrameworkBadge, type BadgeTone } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Field, Select, Textarea, describedBy } from '@/components/ui/Field'
import { SkeletonText } from '@/components/ui/Skeleton'
import { loadClients, type ClientOption } from '@/components/ambito/clients'
import { api } from '@/lib/api'
import { isDemoMode } from '@/lib/auth'
import { getConfidenceLabel } from '@/lib/confidence-labels'
import { formatDateIt } from '@/lib/obligations/dates'
import type { ApiResponse, CompanyProfile, MonitorResponse } from '@/lib/types'
import { SEVERITY_META } from './AlertsTab'

const MIN_LENGTH = 10
const MAX_LENGTH = 5000

/** The same sample profile the previous Monitor page used in demo mode (CompanyProfileForm.tsx). */
const DEMO_PROFILE: CompanyProfile = {
  name: 'Acme Srl',
  sector: 'Manufacturing',
  employee_count: 2500,
  revenue_eur: 200_000_000,
  jurisdictions: ['IT', 'DE', 'FR'],
  applicable_frameworks: ['CSRD', 'DORA', 'NIS2'],
  existing_documents: '',
}

const GENERIC_PROFILE: CompanyProfile = {
  name: 'Impresa senza profilo',
  sector: '',
  employee_count: 0,
  revenue_eur: 0,
  jurisdictions: [],
  applicable_frameworks: [],
  existing_documents: '',
}

/** Urgency agrees with "urgenza" (feminine); the severity labels of the alerts are masculine ("livello"). */
const URGENCY_LABEL: Record<MonitorResponse['urgency'], string> = {
  CRITICAL: 'critica',
  HIGH: 'alta',
  MEDIUM: 'media',
  LOW: 'bassa',
  INFORMATIONAL: 'informativa',
}

const APPLICABILITY_META: Record<MonitorResponse['applicability'], { label: string; tone: BadgeTone }> = {
  YES: { label: 'Si applica', tone: 'union' },
  NO: { label: 'Non si applica', tone: 'neutral' },
  CONDITIONAL: { label: 'Dipende', tone: 'warn' },
}

const EXAMPLE =
  'L’Omnibus I (Direttiva (UE) 2026/470) ha alzato le soglie CSRD a più di 1.000 dipendenti e oltre 450 milioni di euro di ricavi netti, in logica cumulativa.'

function isIsoDate(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value)
}

function profileFor(client: ClientOption): CompanyProfile {
  return {
    name: client.name,
    sector: client.sector ?? '',
    employee_count: client.employee_count ?? 0,
    revenue_eur: client.revenue_eur ?? 0,
    jurisdictions: client.jurisdictions ?? [],
    applicable_frameworks: [],
    existing_documents: '',
  }
}

function MonitorResult({ result }: { result: MonitorResponse }) {
  const applicability = APPLICABILITY_META[result.applicability] ?? { label: result.applicability, tone: 'neutral' as BadgeTone }
  const urgency = SEVERITY_META[result.urgency] ?? { label: result.urgency, tone: 'neutral' as BadgeTone }
  const confidence = getConfidenceLabel(result.confidence_score)
  const deadline = (result.deadline ?? '').trim()

  return (
    <section aria-labelledby="monitor-result-title" className="rounded-lg border border-rule bg-surface">
      <div className="flex flex-wrap items-center gap-2 border-b border-rule px-5 py-3">
        <h3 id="monitor-result-title" className="font-sans text-body font-medium text-ink">
          Risultato dell’analisi
        </h3>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <Badge tone={applicability.tone}>{applicability.label}</Badge>
          <Badge tone={urgency.tone}>Urgenza: {URGENCY_LABEL[result.urgency] ?? urgency.label.toLowerCase()}</Badge>
          {result.requires_expert_review && <Badge tone="warn">Revisione di un esperto consigliata</Badge>}
        </div>
      </div>
      <div className="space-y-5 px-5 py-5">
        <p className="font-serif text-h4 text-ink">{result.applicability_reason}</p>

        <div>
          <h4 className="font-sans text-small font-medium text-ink-2">Impatto</h4>
          <p className="mt-1 text-body text-ink">{result.impact_summary}</p>
        </div>

        {result.required_actions?.length > 0 && (
          <div>
            <h4 className="font-sans text-small font-medium text-ink-2">Azioni richieste</h4>
            <ol className="mt-1 list-decimal space-y-1 pl-5 text-body text-ink">
              {result.required_actions.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ol>
          </div>
        )}

        <div>
          <h4 className="font-sans text-small font-medium text-ink-2">Scadenza</h4>
          <p className="mt-1 flex flex-wrap items-center gap-2 text-body text-ink">
            {deadline ? (
              <>
                <span className={isIsoDate(deadline) ? 'tabular' : undefined}>
                  {isIsoDate(deadline) ? formatDateIt(deadline) : deadline}
                </span>
                {result.deadline_is_confirmed ? (
                  <Badge tone="neutral">Indicata come confermata dall’analisi</Badge>
                ) : (
                  <Badge tone="warn">Data da confermare</Badge>
                )}
              </>
            ) : (
              <span className="text-ink-2">Nessuna scadenza indicata dall’analisi.</span>
            )}
          </p>
        </div>

        {result.cross_framework_impacts?.length > 0 && (
          <div>
            <h4 className="font-sans text-small font-medium text-ink-2">Effetti su altri ambiti</h4>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-body text-ink">
              {result.cross_framework_impacts.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          </div>
        )}

        <div className="border-t border-rule pt-4">
          <h4 className="font-sans text-small font-medium text-ink-2">Riferimenti citati dall’analisi</h4>
          {result.citations?.length > 0 ? (
            <ol className="mt-1.5 space-y-1">
              {result.citations.map((c, i) => (
                <li key={c} className="flex flex-wrap items-baseline gap-x-2 text-small text-ink-2">
                  <span className="tabular text-ink-3">[{i + 1}]</span>
                  <span className="text-ink">{c}</span>
                  <span className="text-caption text-ink-3">Non verificata automaticamente sul testo ufficiale</span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="mt-1 text-small text-ink-2">L’analisi non ha citato riferimenti.</p>
          )}
          <p className="mt-3 flex flex-wrap items-center gap-2 text-caption text-ink-3">
            <Badge tone="neutral">{confidence.label}</Badge>
            <span>
              Analisi generata da un sistema di IA (Regolamento (UE) 2024/1689, art. 50). Verifica sul testo ufficiale
              prima di decisioni vincolanti.
            </span>
          </p>
        </div>
      </div>
    </section>
  )
}

/** The existing /api/v1/monitor flow: a regulatory change, a client profile, the impact assessment. */
export function AnalyzeTab() {
  const [text, setText] = useState('')
  const [clients, setClients] = useState<ClientOption[]>([])
  const [clientsLoading, setClientsLoading] = useState(true)
  const [clientId, setClientId] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<MonitorResponse | null>(null)
  const [frameworksHint, setFrameworksHint] = useState<string[]>([])
  const resultRef = useRef<HTMLDivElement>(null)
  const demo = isDemoMode()

  useEffect(() => {
    let cancelled = false
    loadClients()
      .then((list) => {
        if (!cancelled) setClients(list)
      })
      .catch(() => {
        if (!cancelled) setClients([])
      })
      .finally(() => {
        if (!cancelled) setClientsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const trimmed = text.trim()
  const lengthError =
    trimmed.length > 0 && trimmed.length < MIN_LENGTH
      ? `Descrivi la novità con almeno ${MIN_LENGTH} caratteri.`
      : trimmed.length > MAX_LENGTH
        ? `Il testo supera i ${MAX_LENGTH} caratteri.`
        : undefined

  const submit = async () => {
    if (!trimmed) {
      setError('Incolla o descrivi la novità normativa da analizzare.')
      return
    }
    if (lengthError) {
      setError(lengthError)
      return
    }
    let profile: CompanyProfile
    if (clientId === '__demo') profile = DEMO_PROFILE
    else if (clientId === '__generic' || clientId === '') profile = demo ? DEMO_PROFILE : GENERIC_PROFILE
    else {
      const c = clients.find((x) => x.id === clientId)
      profile = c ? profileFor(c) : GENERIC_PROFILE
    }

    setError('')
    setLoading(true)
    setResult(null)
    try {
      const res = await api.post<ApiResponse<MonitorResponse>>('/api/v1/monitor', {
        regulation_change: trimmed,
        company_profile: profile,
      })
      setResult(res.data)
      setFrameworksHint(profile.applicable_frameworks)
      window.setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'L’analisi non è riuscita. Riprova tra un minuto.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="grid gap-8 lg:grid-cols-12">
      <form
        noValidate
        className="space-y-5 lg:col-span-5"
        onSubmit={(e) => {
          e.preventDefault()
          submit()
        }}
      >
        <Field
          label="Novità normativa"
          htmlFor="monitor-text"
          help={`Incolla il testo o descrivi la modifica: da ${MIN_LENGTH} a ${MAX_LENGTH} caratteri.`}
          error={lengthError}
          required
        >
          <Textarea
            id="monitor-text"
            value={text}
            onChange={(e) => {
              setText(e.target.value)
              if (error) setError('')
            }}
            rows={7}
            maxLength={MAX_LENGTH + 500}
            placeholder={`Per esempio: ${EXAMPLE}`}
            invalid={!!lengthError}
            aria-describedby={describedBy('monitor-text', { help: true, error: lengthError })}
          />
        </Field>
        <div className="flex flex-wrap items-center gap-2 text-small text-ink-3">
          <span>Prova con un esempio:</span>
          <button
            type="button"
            onClick={() => setText(EXAMPLE)}
            className="rounded-md border border-rule bg-surface px-2.5 py-1 text-left text-small text-ink-2 hover:border-rule-2 hover:text-ink"
          >
            Soglie CSRD dopo l’Omnibus I
          </button>
        </div>

        <Field
          label="Profilo dell’impresa"
          htmlFor="monitor-client"
          help={
            demo
              ? 'Demo con dati di esempio: senza una scelta, l’analisi usa il profilo di esempio Acme Srl.'
              : 'L’analisi usa dipendenti, ricavi e Paesi del cliente scelto.'
          }
        >
          <Select id="monitor-client" value={clientId} disabled={clientsLoading} onChange={(e) => setClientId(e.target.value)}>
            {demo ? (
              <option value="__demo">Profilo di esempio (Acme Srl, 2.500 dipendenti)</option>
            ) : (
              <option value="__generic">Senza profilo cliente (analisi generica)</option>
            )}
            {clients.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
        </Field>

        {error && (
          <p className="text-small text-bad" role="alert">
            {error}
          </p>
        )}

        <Button type="submit" loading={loading}>
          Analizza la novità
        </Button>
        {frameworksHint.length > 0 && result && (
          <p className="flex flex-wrap items-center gap-1.5 text-caption text-ink-3">
            <span>Ambiti del profilo usato:</span>
            {frameworksHint.map((f) => (
              <FrameworkBadge key={f} framework={f.replace(' ', '_').toUpperCase()} />
            ))}
          </p>
        )}
      </form>

      <div className="scroll-mt-20 lg:col-span-7" ref={resultRef}>
        {loading ? (
          <div className="rounded-lg border border-rule bg-surface px-5 py-5" role="status" aria-label="Analisi in corso">
            <p className="text-small text-ink-2">Analisi in corso: può richiedere fino a un minuto.</p>
            <SkeletonText lines={4} className="mt-3" />
          </div>
        ) : result ? (
          <MonitorResult result={result} />
        ) : (
          <div className="rounded-lg border border-dashed border-rule-2 px-6 py-12 text-center">
            <p className="text-h4">Incolla una novità e premi Analizza la novità</p>
            <p className="mt-2 text-small text-ink-2">
              Il risultato dice se la novità si applica al profilo scelto, con quale urgenza, cosa fare e entro quando.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
