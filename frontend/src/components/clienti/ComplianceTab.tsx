'use client'

import { useEffect, useState, type FormEvent } from 'react'
import { useTranslations } from 'next-intl'
import { ClipboardCheck } from 'lucide-react'
import { Button, EmptyState, Field, Select, frameworkLabel } from '@/components/ui'
import { useErrorText } from '@/i18n/errors'
import { api } from '@/lib/api'
import type { ApiResponse, Client, CompanyProfile, GapAnalysisResponse, Requirement } from '@/lib/types'
import { FRAMEWORK_KEYS, isFrameworkKey, type FrameworkKey } from './clients-api'
import { formatIsoDateTime } from './format'
import { RequirementsChecklist, checklistCounts } from './RequirementsChecklist'

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
 * The requirements of one framework for one client. No document of the
 * client is sent to the gap-analysis endpoint, so its verdicts and score
 * would rest on missing evidence: the tab shows the list of requirements
 * with their articles, each to be checked (see RequirementsChecklist).
 */
export function ComplianceTab({ client }: { client: Client }) {
  const t = useTranslations('clienti.compliance')
  const tRoot = useTranslations()
  const errorText = useErrorText()
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
      setError(errorText(err, 'clienti.compliance.failed'))
    } finally {
      setLoading(false)
    }
  }

  const result = analysis?.result
  const requirements: Requirement[] = result?.requirements ?? []
  const counts = checklistCounts(requirements)

  return (
    <div className="space-y-6">
      <form onSubmit={run} className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <Field label={t('framework')} htmlFor="gap-framework" className="w-full sm:max-w-xs">
          <Select
            id="gap-framework"
            value={framework}
            onChange={(e) => setFramework(e.target.value as FrameworkKey)}
            disabled={loading}
          >
            {FRAMEWORK_KEYS.map((key) => (
              <option key={key} value={key}>
                {frameworkLabel(key, tRoot)}
              </option>
            ))}
          </Select>
        </Field>
        <Button type="submit" loading={loading} iconLeft={<ClipboardCheck className="h-4 w-4" aria-hidden="true" />}>
          {loading ? t('running') : analysis ? t('rerun') : t('run')}
        </Button>
      </form>

      {loading && (
        <p role="status" className="rounded-md border border-rule bg-surface-2 px-4 py-3 text-small text-ink-2">
          {t('progress', { name: client.name, framework: frameworkLabel(framework, tRoot) })}
        </p>
      )}

      {error && (
        <div role="alert" className="rounded-lg border border-bad/30 bg-surface p-5">
          <h3 className="text-h4">{t('failedTitle')}</h3>
          <p className="mt-1 text-body text-ink-2">{error}</p>
        </div>
      )}

      {!loading && !result && !error && (
        <EmptyState
          icon={<ClipboardCheck className="h-8 w-8" aria-hidden="true" />}
          title={t('emptyTitle')}
          description={t('emptyDescription')}
        />
      )}

      {result && analysis && (
        <section className="space-y-4" aria-labelledby="gap-result-title">
          <div>
            <h3 id="gap-result-title" className="text-h3">
              {t('resultTitle', { framework: frameworkLabel(analysis.framework, tRoot) })}
            </h3>
            <p className="mt-1 text-caption text-ink-3 tabular">
              {t('analysedOn', { date: formatIsoDateTime(analysis.analysedAt) ?? '' })}
            </p>
            <p className="mt-3 max-w-prose text-body text-ink-2">{t('explain')}</p>
            {requirements.length > 0 && (
              <p className="mt-2 text-small text-ink-2">
                {t('counts', { toVerify: counts.toVerify, notApplicable: counts.notApplicable })}
              </p>
            )}
          </div>

          {requirements.length > 0 ? (
            <RequirementsChecklist requirements={requirements} labelledBy="gap-result-title" />
          ) : (
            <p className="text-body text-ink-2">{t('noRequirements')}</p>
          )}

          <p className="max-w-prose text-caption text-ink-3">{t('aiNotice')}</p>
        </section>
      )}
    </div>
  )
}
