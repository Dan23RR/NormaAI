'use client'

import { useState, useCallback } from 'react'
import type { CompanyProfile } from '@/lib/types'
import { FRAMEWORKS } from '@/lib/types'
import { isDemoMode } from '@/lib/auth'
import { ChevronDown, ChevronUp, AlertCircle } from 'lucide-react'

interface Props {
  value: CompanyProfile
  onChange: (profile: CompanyProfile) => void
  required?: boolean
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

export function validateProfile(profile: CompanyProfile, required: boolean): ValidationErrors {
  const errors: ValidationErrors = {}

  if (required || profile.name) {
    if (!profile.name.trim()) {
      errors.name = 'Il nome azienda è obbligatorio'
    } else if (profile.name.trim().length < 2) {
      errors.name = 'Il nome deve avere almeno 2 caratteri'
    }
  }

  if (profile.employee_count < 0) {
    errors.employee_count = 'Il numero dipendenti non può essere negativo'
  } else if (profile.employee_count > 10_000_000) {
    errors.employee_count = 'Valore non valido'
  }

  if (profile.revenue_eur < 0) {
    errors.revenue_eur = 'Il fatturato non può essere negativo'
  }

  if (required && profile.applicable_frameworks.length === 0) {
    errors.applicable_frameworks = 'Seleziona almeno un framework'
  }

  return errors
}

export default function CompanyProfileForm({ value, onChange, required }: Props) {
  const [expanded, setExpanded] = useState(!!required)
  const [touched, setTouched] = useState<Set<string>>(new Set())

  const errors = validateProfile(value, !!required)
  const hasErrors = Object.keys(errors).length > 0

  const update = useCallback((field: keyof CompanyProfile, val: unknown) => {
    onChange({ ...value, [field]: val })
  }, [value, onChange])

  const markTouched = useCallback((field: string) => {
    setTouched((prev) => new Set(prev).add(field))
  }, [])

  const showError = (field: keyof ValidationErrors) =>
    touched.has(field) && errors[field]

  return (
    <div className={`bg-surface border rounded-xl overflow-hidden ${
      hasErrors && touched.size > 0 ? 'border-yellow-500/30' : 'border-white/[0.06]'
    }`}>
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-slate-300 hover:bg-white/[0.02] transition"
        aria-expanded={expanded}
      >
        <span className="flex items-center gap-2">
          Company Profile {required && <span className="text-red-400">*</span>}
          {hasErrors && touched.size > 0 && (
            <AlertCircle size={14} className="text-yellow-400" />
          )}
        </span>
        {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-white/[0.04]">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-3">
            <div>
              <label htmlFor="cp-name" className="block text-xs text-slate-500 mb-1">Company name</label>
              <input
                id="cp-name"
                type="text"
                value={value.name}
                onChange={(e) => update('name', e.target.value)}
                onBlur={() => markTouched('name')}
                maxLength={200}
                className={`w-full px-3 py-2 bg-surface2 border rounded-lg text-sm text-white focus:outline-none transition ${
                  showError('name') ? 'border-red-400/50 focus:border-red-400' : 'border-white/[0.06] focus:border-accent/40'
                }`}
                placeholder="e.g. Acme Srl"
                aria-invalid={!!showError('name')}
                aria-describedby={showError('name') ? 'cp-name-error' : undefined}
              />
              {showError('name') && (
                <p id="cp-name-error" className="text-[11px] text-red-400 mt-1" role="alert">{errors.name}</p>
              )}
            </div>
            <div>
              <label htmlFor="cp-sector" className="block text-xs text-slate-500 mb-1">Sector</label>
              <input
                id="cp-sector"
                type="text"
                value={value.sector}
                onChange={(e) => update('sector', e.target.value)}
                onBlur={() => markTouched('sector')}
                maxLength={100}
                className="w-full px-3 py-2 bg-surface2 border border-white/[0.06] rounded-lg text-sm text-white focus:outline-none focus:border-accent/40 transition"
                placeholder="e.g. Manufacturing"
              />
            </div>
            <div>
              <label htmlFor="cp-employees" className="block text-xs text-slate-500 mb-1">Employees</label>
              <input
                id="cp-employees"
                type="number"
                value={value.employee_count || ''}
                onChange={(e) => update('employee_count', Math.max(0, parseInt(e.target.value) || 0))}
                onBlur={() => markTouched('employee_count')}
                min={0}
                max={10000000}
                className={`w-full px-3 py-2 bg-surface2 border rounded-lg text-sm text-white focus:outline-none transition ${
                  showError('employee_count') ? 'border-red-400/50 focus:border-red-400' : 'border-white/[0.06] focus:border-accent/40'
                }`}
                placeholder="e.g. 2500"
                aria-invalid={!!showError('employee_count')}
              />
              {showError('employee_count') && (
                <p className="text-[11px] text-red-400 mt-1" role="alert">{errors.employee_count}</p>
              )}
            </div>
            <div>
              <label htmlFor="cp-revenue" className="block text-xs text-slate-500 mb-1">Revenue (EUR)</label>
              <input
                id="cp-revenue"
                type="number"
                value={value.revenue_eur || ''}
                onChange={(e) => update('revenue_eur', Math.max(0, parseInt(e.target.value) || 0))}
                onBlur={() => markTouched('revenue_eur')}
                min={0}
                className={`w-full px-3 py-2 bg-surface2 border rounded-lg text-sm text-white focus:outline-none transition ${
                  showError('revenue_eur') ? 'border-red-400/50 focus:border-red-400' : 'border-white/[0.06] focus:border-accent/40'
                }`}
                placeholder="e.g. 200000000"
                aria-invalid={!!showError('revenue_eur')}
              />
              {showError('revenue_eur') && (
                <p className="text-[11px] text-red-400 mt-1" role="alert">{errors.revenue_eur}</p>
              )}
            </div>
          </div>

          <div>
            <label htmlFor="cp-jurisdictions" className="block text-xs text-slate-500 mb-1">Jurisdictions (comma-separated)</label>
            <input
              id="cp-jurisdictions"
              type="text"
              value={value.jurisdictions.join(', ')}
              onChange={(e) => update('jurisdictions', e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
              className="w-full px-3 py-2 bg-surface2 border border-white/[0.06] rounded-lg text-sm text-white focus:outline-none focus:border-accent/40 transition"
              placeholder="e.g. IT, DE, FR"
            />
          </div>

          <div>
            <label className="block text-xs text-slate-500 mb-2">Applicable frameworks</label>
            <div className="flex flex-wrap gap-2" role="group" aria-label="Framework selection">
              {FRAMEWORKS.map((fw) => {
                const selected = value.applicable_frameworks.includes(fw.value)
                return (
                  <button
                    key={fw.value}
                    type="button"
                    onClick={() => {
                      const updated = selected
                        ? value.applicable_frameworks.filter(f => f !== fw.value)
                        : [...value.applicable_frameworks, fw.value]
                      update('applicable_frameworks', updated)
                      markTouched('applicable_frameworks')
                    }}
                    className={`px-2.5 py-1 rounded-md text-xs font-medium border transition ${
                      selected
                        ? 'border-accent/40 bg-accent/10 text-accent'
                        : 'border-white/[0.06] text-slate-500 hover:text-slate-300'
                    }`}
                    aria-pressed={selected}
                  >
                    {fw.value}
                  </button>
                )
              })}
            </div>
            {showError('applicable_frameworks') && (
              <p className="text-[11px] text-red-400 mt-1.5" role="alert">{errors.applicable_frameworks}</p>
            )}
          </div>

          <div>
            <label htmlFor="cp-docs" className="block text-xs text-slate-500 mb-1">Existing compliance documents</label>
            <textarea
              id="cp-docs"
              value={value.existing_documents}
              onChange={(e) => update('existing_documents', e.target.value)}
              rows={2}
              maxLength={2000}
              className="w-full px-3 py-2 bg-surface2 border border-white/[0.06] rounded-lg text-sm text-white focus:outline-none focus:border-accent/40 resize-none transition"
              placeholder="e.g. Annual sustainability report, GDPR compliance manual..."
            />
          </div>
        </div>
      )}
    </div>
  )
}
