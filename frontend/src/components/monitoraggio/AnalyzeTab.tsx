'use client'

import { useEffect, useRef, useState } from 'react'
import { useTranslations } from 'next-intl'
import { Badge, FrameworkBadge, type BadgeTone } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Field, Select, Textarea, describedBy } from '@/components/ui/Field'
import { SkeletonText } from '@/components/ui/Skeleton'
import { loadClients, type ClientOption } from '@/components/ambito/clients'
import { useErrorText } from '@/i18n/errors'
import { useDateFormat } from '@/i18n/useDateFormat'
import { useTextContext } from '@/i18n/useTextContext'
import { api } from '@/lib/api'
import { isDemoMode } from '@/lib/auth'
import { getConfidenceLabel } from '@/lib/confidence-labels'
import type { ApiResponse, CompanyProfile, MonitorResponse } from '@/lib/types'
import { SEVERITIES, SEVERITY_TONE, severityLabel } from './AlertsTab'

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

const APPLICABILITY_TONE: Record<MonitorResponse['applicability'], BadgeTone> = {
  YES: 'union',
  NO: 'neutral',
  CONDITIONAL: 'warn',
}

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
  const t = useTranslations('monitoraggio.analyze')
  const ctx = useTextContext()
  const formatDate = useDateFormat()
  const applicabilityTone = APPLICABILITY_TONE[result.applicability] ?? 'neutral'
  const applicabilityLabel = result.applicability in APPLICABILITY_TONE ? t(`applicability.${result.applicability}`) : result.applicability
  const urgencyTone = SEVERITY_TONE[result.urgency] ?? 'neutral'
  const urgency = (SEVERITIES as string[]).includes(result.urgency)
    ? t(`urgency.${result.urgency}`)
    : severityLabel(result.urgency, ctx.t).toLowerCase()
  const confidence = getConfidenceLabel(result.confidence_score, ctx.t)
  const deadline = (result.deadline ?? '').trim()

  return (
    <section aria-labelledby="monitor-result-title" className="rounded-lg border border-rule bg-surface">
      <div className="flex flex-wrap items-center gap-2 border-b border-rule px-5 py-3">
        <h3 id="monitor-result-title" className="font-sans text-body font-medium text-ink">
          {t('resultTitle')}
        </h3>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <Badge tone={applicabilityTone}>{applicabilityLabel}</Badge>
          <Badge tone={urgencyTone}>{t('urgencyLabel', { urgency })}</Badge>
          {result.requires_expert_review && <Badge tone="warn">{t('expertReview')}</Badge>}
        </div>
      </div>
      <div className="space-y-5 px-5 py-5">
        <p className="font-serif text-h4 text-ink">{result.applicability_reason}</p>

        <div>
          <h4 className="font-sans text-small font-medium text-ink-2">{t('impact')}</h4>
          <p className="mt-1 text-body text-ink">{result.impact_summary}</p>
        </div>

        {result.required_actions?.length > 0 && (
          <div>
            <h4 className="font-sans text-small font-medium text-ink-2">{t('actions')}</h4>
            <ol className="mt-1 list-decimal space-y-1 pl-5 text-body text-ink">
              {result.required_actions.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ol>
          </div>
        )}

        <div>
          <h4 className="font-sans text-small font-medium text-ink-2">{t('deadline')}</h4>
          <p className="mt-1 flex flex-wrap items-center gap-2 text-body text-ink">
            {deadline ? (
              <>
                <span className={isIsoDate(deadline) ? 'tabular' : undefined}>
                  {isIsoDate(deadline) ? formatDate(deadline) : deadline}
                </span>
                {result.deadline_is_confirmed ? (
                  <Badge tone="neutral">{t('deadlineConfirmed')}</Badge>
                ) : (
                  <Badge tone="warn">{t('deadlineUnconfirmed')}</Badge>
                )}
              </>
            ) : (
              <span className="text-ink-2">{t('noDeadline')}</span>
            )}
          </p>
        </div>

        {result.cross_framework_impacts?.length > 0 && (
          <div>
            <h4 className="font-sans text-small font-medium text-ink-2">{t('crossImpacts')}</h4>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-body text-ink">
              {result.cross_framework_impacts.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          </div>
        )}

        <div className="border-t border-rule pt-4">
          <h4 className="font-sans text-small font-medium text-ink-2">{t('citations')}</h4>
          {result.citations?.length > 0 ? (
            <ol className="mt-1.5 space-y-1">
              {result.citations.map((c, i) => (
                <li key={c} className="flex flex-wrap items-baseline gap-x-2 text-small text-ink-2">
                  <span className="tabular text-ink-3">[{i + 1}]</span>
                  <span className="text-ink">{c}</span>
                  <span className="text-caption text-ink-3">{t('citationUnverified')}</span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="mt-1 text-small text-ink-2">{t('noCitations')}</p>
          )}
          <p className="mt-3 flex flex-wrap items-center gap-2 text-caption text-ink-3">
            <Badge tone="neutral">{confidence.label}</Badge>
            <span>{t('aiNotice')}</span>
          </p>
        </div>
      </div>
    </section>
  )
}

/** The existing /api/v1/monitor flow: a regulatory change, a client profile, the impact assessment. */
export function AnalyzeTab() {
  const t = useTranslations('monitoraggio.analyze')
  const errorText = useErrorText()
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
  const limits = { min: String(MIN_LENGTH), max: String(MAX_LENGTH) }

  const genericProfile: CompanyProfile = {
    name: t('genericName'),
    sector: '',
    employee_count: 0,
    revenue_eur: 0,
    jurisdictions: [],
    applicable_frameworks: [],
    existing_documents: '',
  }

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
      ? t('tooShort', limits)
      : trimmed.length > MAX_LENGTH
        ? t('tooLong', limits)
        : undefined

  const submit = async () => {
    if (!trimmed) {
      setError(t('required'))
      return
    }
    if (lengthError) {
      setError(lengthError)
      return
    }
    let profile: CompanyProfile
    if (clientId === '__demo') profile = DEMO_PROFILE
    else if (clientId === '__generic' || clientId === '') profile = demo ? DEMO_PROFILE : genericProfile
    else {
      const c = clients.find((x) => x.id === clientId)
      profile = c ? profileFor(c) : genericProfile
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
      setError(errorText(e, 'monitoraggio.analyze.failed'))
    } finally {
      setLoading(false)
    }
  }

  const example = t('example')

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
        <Field label={t('text')} htmlFor="monitor-text" help={t('textHelp', limits)} error={lengthError} required>
          <Textarea
            id="monitor-text"
            value={text}
            onChange={(e) => {
              setText(e.target.value)
              if (error) setError('')
            }}
            rows={7}
            maxLength={MAX_LENGTH + 500}
            placeholder={t('placeholder', { example })}
            invalid={!!lengthError}
            aria-describedby={describedBy('monitor-text', { help: true, error: lengthError })}
          />
        </Field>
        <div className="flex flex-wrap items-center gap-2 text-small text-ink-3">
          <span>{t('examples')}</span>
          <button
            type="button"
            onClick={() => setText(example)}
            className="rounded-md border border-rule bg-surface px-2.5 py-1 text-left text-small text-ink-2 hover:border-rule-2 hover:text-ink"
          >
            {t('exampleLabel')}
          </button>
        </div>

        <Field label={t('profile')} htmlFor="monitor-client" help={demo ? t('profileHelpDemo') : t('profileHelp')}>
          <Select id="monitor-client" value={clientId} disabled={clientsLoading} onChange={(e) => setClientId(e.target.value)}>
            {demo ? <option value="__demo">{t('demoProfile')}</option> : <option value="__generic">{t('genericProfile')}</option>}
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
          {t('submit')}
        </Button>
        {frameworksHint.length > 0 && result && (
          <p className="flex flex-wrap items-center gap-1.5 text-caption text-ink-3">
            <span>{t('frameworksUsed')}</span>
            {frameworksHint.map((f) => (
              <FrameworkBadge key={f} framework={f.replace(' ', '_').toUpperCase()} />
            ))}
          </p>
        )}
      </form>

      <div className="scroll-mt-20 lg:col-span-7" ref={resultRef}>
        {loading ? (
          <div className="rounded-lg border border-rule bg-surface px-5 py-5" role="status" aria-label={t('loadingLabel')}>
            <p className="text-small text-ink-2">{t('loading')}</p>
            <SkeletonText lines={4} className="mt-3" />
          </div>
        ) : result ? (
          <MonitorResult result={result} />
        ) : (
          <div className="rounded-lg border border-dashed border-rule-2 px-6 py-12 text-center">
            <p className="text-h4">{t('emptyTitle')}</p>
            <p className="mt-2 text-small text-ink-2">{t('emptyDescription')}</p>
          </div>
        )}
      </div>
    </div>
  )
}
