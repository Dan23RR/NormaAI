'use client'

import { useCallback, useId, useState } from 'react'
import { useTranslations } from 'next-intl'
import { ChevronDown, AlertTriangle } from 'lucide-react'
import type { CompanyProfile } from '@/lib/types'
import { FRAMEWORKS } from '@/lib/types'
import { isDemoMode } from '@/lib/auth'
import { Card } from '@/components/ui/Card'
import { Field, Input, Textarea, describedBy } from '@/components/ui/Field'
import { frameworkLabel } from '@/components/ui/Badge'
import { cn } from '@/lib/cn'
import { formatInt } from '@/i18n/format'
import type { TextContext, Translate } from '@/i18n/types'
import { useTextContext } from '@/i18n/useTextContext'

interface Props {
  value: CompanyProfile
  onChange: (profile: CompanyProfile) => void
  /** When true the profile is needed (gap analysis, monitoring): the panel opens and the name is mandatory. */
  required?: boolean
  /** Prefix for the control ids, so two instances of the form can live on one page. */
  idPrefix?: string
  /** Open the panel at first render (defaults to `required`). */
  defaultExpanded?: boolean
  className?: string
}

interface ValidationErrors {
  name?: string
  sector?: string
  employee_count?: string
  revenue_eur?: string
  jurisdictions?: string
  applicable_frameworks?: string
}

const defaultProfile: CompanyProfile = {
  name: '',
  sector: '',
  employee_count: 0,
  revenue_eur: 0,
  jurisdictions: [],
  applicable_frameworks: [],
  existing_documents: '',
}

const demoProfile: CompanyProfile = {
  name: 'Acme Srl',
  sector: 'Manufacturing',
  employee_count: 2500,
  revenue_eur: 200_000_000,
  jurisdictions: ['IT', 'DE', 'FR'],
  applicable_frameworks: ['CSRD', 'DORA', 'NIS2'],
  existing_documents: '',
}

const PROFILE_STORAGE_KEY = 'normaai_company_profile'

function loadStoredProfile(): CompanyProfile | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = sessionStorage.getItem(PROFILE_STORAGE_KEY)
    if (raw) return JSON.parse(raw)
  } catch { /* ignore */ }
  return null
}

export function useCompanyProfile(initial?: Partial<CompanyProfile>) {
  const base = isDemoMode() ? demoProfile : defaultProfile
  const [profile, setProfileRaw] = useState<CompanyProfile>(() => {
    const stored = loadStoredProfile()
    return stored ?? { ...base, ...initial }
  })
  const setProfile = useCallback((p: CompanyProfile) => {
    setProfileRaw(p)
    try { sessionStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(p)) } catch { /* ignore */ }
  }, [])
  return { profile, setProfile }
}

export function validateProfile(profile: CompanyProfile, required: boolean, t: Translate): ValidationErrors {
  const errors: ValidationErrors = {}

  if (required || profile.name) {
    if (!profile.name.trim()) {
      errors.name = t('chiedi.profile.errors.nameRequired')
    } else if (profile.name.trim().length < 2) {
      errors.name = t('chiedi.profile.errors.nameShort')
    }
  }

  if (profile.employee_count < 0) {
    errors.employee_count = t('chiedi.profile.errors.employeesNegative')
  } else if (profile.employee_count > 10_000_000) {
    errors.employee_count = t('chiedi.profile.errors.employeesInvalid')
  }

  if (profile.revenue_eur < 0) {
    errors.revenue_eur = t('chiedi.profile.errors.revenueNegative')
  }

  if (required && profile.applicable_frameworks.length === 0) {
    errors.applicable_frameworks = t('chiedi.profile.errors.frameworksRequired')
  }

  return errors
}

/** One line that says what will be sent with the question. */
export function profileSummary(profile: CompanyProfile, ctx: TextContext): string | null {
  const name = profile.name.trim()
  if (!name) return null
  const parts = [name]
  if (profile.sector.trim()) parts.push(profile.sector.trim())
  if (profile.employee_count > 0) parts.push(ctx.t('chiedi.profile.employeesSummary', { count: formatInt(profile.employee_count, ctx.locale) }))
  if (profile.jurisdictions.length) parts.push(profile.jurisdictions.join(', '))
  return parts.join(', ')
}

/**
 * The optional company profile: a collapsible panel with the facts that
 * let the answer speak about this company (size, sector, countries,
 * frameworks already in scope). Same validation and storage as before.
 */
export default function CompanyProfileForm({
  value,
  onChange,
  required,
  idPrefix = 'cp',
  defaultExpanded,
  className,
}: Props) {
  const t = useTranslations('chiedi.profile')
  const ctx = useTextContext()
  const [expanded, setExpanded] = useState(defaultExpanded ?? !!required)
  const [touched, setTouched] = useState<Set<string>>(new Set())
  const panelId = `${idPrefix}-${useId().replace(/[^a-zA-Z0-9_-]/g, '')}-panel`

  const errors = validateProfile(value, !!required, ctx.t)
  const hasErrors = Object.keys(errors).length > 0
  const showWarning = hasErrors && touched.size > 0

  const update = useCallback((field: keyof CompanyProfile, val: unknown) => {
    onChange({ ...value, [field]: val })
  }, [value, onChange])

  const markTouched = useCallback((field: string) => {
    setTouched((prev) => new Set(prev).add(field))
  }, [])

  const errorFor = (field: keyof ValidationErrors) => (touched.has(field) ? errors[field] : undefined)

  const summary = profileSummary(value, ctx)
  const ids = {
    name: `${idPrefix}-name`,
    sector: `${idPrefix}-sector`,
    employees: `${idPrefix}-employees`,
    revenue: `${idPrefix}-revenue`,
    jurisdictions: `${idPrefix}-jurisdictions`,
    docs: `${idPrefix}-docs`,
  }

  return (
    <Card className={cn(showWarning && 'border-warn/60', className)}>
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        aria-controls={panelId}
        className="flex w-full items-start justify-between gap-3 rounded-lg px-4 py-3 text-left hover:bg-surface-2"
      >
        <span className="min-w-0">
          <span className="flex items-center gap-2 text-body font-medium text-ink">
            {t('title')}
            {!required && ` ${t('optional')}`}
            {showWarning && <AlertTriangle className="h-4 w-4 shrink-0 text-warn" aria-label={t('hasErrors')} />}
          </span>
          <span className="mt-0.5 block truncate text-caption text-ink-3" title={summary ?? undefined}>
            {summary ?? t('placeholder')}
          </span>
        </span>
        <ChevronDown
          className={cn('mt-1 h-4 w-4 shrink-0 text-ink-3 transition-transform', expanded && 'rotate-180')}
          aria-hidden="true"
        />
      </button>

      {expanded && (
        <div id={panelId} className="space-y-4 border-t border-rule px-4 pb-4 pt-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t('name')} htmlFor={ids.name} required={required} error={errorFor('name')}>
              <Input
                id={ids.name}
                type="text"
                value={value.name}
                onChange={(e) => update('name', e.target.value)}
                onBlur={() => markTouched('name')}
                maxLength={200}
                placeholder={t('namePlaceholder')}
                autoComplete="organization"
                invalid={!!errorFor('name')}
                aria-describedby={describedBy(ids.name, { error: errorFor('name') })}
              />
            </Field>
            <Field label={t('sector')} htmlFor={ids.sector}>
              <Input
                id={ids.sector}
                type="text"
                value={value.sector}
                onChange={(e) => update('sector', e.target.value)}
                onBlur={() => markTouched('sector')}
                maxLength={100}
                placeholder={t('sectorPlaceholder')}
              />
            </Field>
            <Field label={t('employees')} htmlFor={ids.employees} error={errorFor('employee_count')}>
              <Input
                id={ids.employees}
                type="number"
                inputMode="numeric"
                value={value.employee_count || ''}
                onChange={(e) => update('employee_count', Math.max(0, parseInt(e.target.value) || 0))}
                onBlur={() => markTouched('employee_count')}
                min={0}
                max={10000000}
                placeholder="2500"
                className="tabular"
                invalid={!!errorFor('employee_count')}
                aria-describedby={describedBy(ids.employees, { error: errorFor('employee_count') })}
              />
            </Field>
            <Field label={t('revenue')} htmlFor={ids.revenue} error={errorFor('revenue_eur')}>
              <Input
                id={ids.revenue}
                type="number"
                inputMode="numeric"
                value={value.revenue_eur || ''}
                onChange={(e) => update('revenue_eur', Math.max(0, parseInt(e.target.value) || 0))}
                onBlur={() => markTouched('revenue_eur')}
                min={0}
                placeholder="200000000"
                className="tabular"
                invalid={!!errorFor('revenue_eur')}
                aria-describedby={describedBy(ids.revenue, { error: errorFor('revenue_eur') })}
              />
            </Field>
          </div>

          <Field label={t('countries')} htmlFor={ids.jurisdictions} help={t('countriesHelp')}>
            <Input
              id={ids.jurisdictions}
              type="text"
              value={value.jurisdictions.join(', ')}
              onChange={(e) => update('jurisdictions', e.target.value.split(',').map((s) => s.trim()).filter(Boolean))}
              placeholder="IT, DE, FR"
              aria-describedby={describedBy(ids.jurisdictions, { help: true })}
            />
          </Field>

          <div className="space-y-1.5">
            <p id={`${idPrefix}-frameworks-label`} className="text-small font-medium text-ink">
              {t('frameworks')}
            </p>
            <div className="flex flex-wrap gap-2" role="group" aria-labelledby={`${idPrefix}-frameworks-label`}>
              {FRAMEWORKS.map((fw) => {
                const selected = value.applicable_frameworks.includes(fw.value)
                return (
                  <button
                    key={fw.value}
                    type="button"
                    onClick={() => {
                      const updated = selected
                        ? value.applicable_frameworks.filter((f) => f !== fw.value)
                        : [...value.applicable_frameworks, fw.value]
                      update('applicable_frameworks', updated)
                      markTouched('applicable_frameworks')
                    }}
                    aria-pressed={selected}
                    className={cn(
                      'rounded-md border px-2.5 py-1 text-small font-medium transition-colors',
                      selected
                        ? 'border-union bg-union/10 text-union'
                        : 'border-rule-2 text-ink-2 hover:bg-surface-2 hover:text-ink',
                    )}
                  >
                    {frameworkLabel(fw.value, ctx.t)}
                  </button>
                )
              })}
            </div>
            {errorFor('applicable_frameworks') && (
              <p className="text-caption text-bad" role="alert">
                {errors.applicable_frameworks}
              </p>
            )}
          </div>

          <Field label={t('documents')} htmlFor={ids.docs}>
            <Textarea
              id={ids.docs}
              value={value.existing_documents}
              onChange={(e) => update('existing_documents', e.target.value)}
              rows={2}
              maxLength={2000}
              placeholder={t('documentsPlaceholder')}
              className="min-h-[72px] resize-y"
            />
          </Field>
        </div>
      )}
    </Card>
  )
}
