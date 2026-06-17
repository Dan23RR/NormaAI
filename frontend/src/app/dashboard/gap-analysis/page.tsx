'use client'

import { useState, useEffect } from 'react'
import { api } from '@/lib/api'
import type { GapAnalysisResponse, ApiResponse, Framework, ComplianceStatus } from '@/lib/types'
import { FRAMEWORKS } from '@/lib/types'
import CompanyProfileForm, { useCompanyProfile } from '@/components/CompanyProfileForm'
import { ClipboardCheck, Loader2, AlertTriangle, CheckCircle, XCircle, MinusCircle, ShieldCheck } from 'lucide-react'
import { getConfidenceLabel, getComplianceLabel, COMPLIANCE_STATUS_COLORS } from '@/lib/confidence-labels'

const GAP_STORAGE_KEY = 'normaai_gap_result'
const GAP_SCORES_KEY = 'normaai_gap_scores'

/** Save framework score to sessionStorage for analytics radar chart */
function saveGapScore(fw: string, score: number) {
  try {
    const stored = sessionStorage.getItem(GAP_SCORES_KEY)
    const scores: Record<string, number> = stored ? JSON.parse(stored) : {}
    scores[fw] = score
    sessionStorage.setItem(GAP_SCORES_KEY, JSON.stringify(scores))
  } catch { /* ignore */ }
}

const STATUS_CONFIG: Record<ComplianceStatus, { label: string; color: string; bg: string; icon: React.ElementType }> = {
  COMPLIANT: { label: COMPLIANCE_STATUS_COLORS.COMPLIANT.label, color: COMPLIANCE_STATUS_COLORS.COMPLIANT.color, bg: COMPLIANCE_STATUS_COLORS.COMPLIANT.bg, icon: CheckCircle },
  PARTIALLY_COMPLIANT: { label: COMPLIANCE_STATUS_COLORS.PARTIALLY_COMPLIANT.label, color: COMPLIANCE_STATUS_COLORS.PARTIALLY_COMPLIANT.color, bg: COMPLIANCE_STATUS_COLORS.PARTIALLY_COMPLIANT.bg, icon: MinusCircle },
  NON_COMPLIANT: { label: COMPLIANCE_STATUS_COLORS.NON_COMPLIANT.label, color: COMPLIANCE_STATUS_COLORS.NON_COMPLIANT.color, bg: COMPLIANCE_STATUS_COLORS.NON_COMPLIANT.bg, icon: XCircle },
  NOT_APPLICABLE: { label: COMPLIANCE_STATUS_COLORS.NOT_APPLICABLE.label, color: COMPLIANCE_STATUS_COLORS.NOT_APPLICABLE.color, bg: COMPLIANCE_STATUS_COLORS.NOT_APPLICABLE.bg, icon: MinusCircle },
  IN_EVOLUTION: { label: COMPLIANCE_STATUS_COLORS.IN_EVOLUTION.label, color: COMPLIANCE_STATUS_COLORS.IN_EVOLUTION.color, bg: COMPLIANCE_STATUS_COLORS.IN_EVOLUTION.bg, icon: MinusCircle },
}

export default function GapAnalysisPage() {
  const [framework, setFramework] = useState<Framework>(() => {
    if (typeof window === 'undefined') return 'CSRD'
    try {
      const r = sessionStorage.getItem(GAP_STORAGE_KEY)
      if (r) { const parsed = JSON.parse(r); return (parsed.framework as Framework) || 'CSRD' }
    } catch { /* */ }
    return 'CSRD'
  })
  const { profile, setProfile } = useCompanyProfile()
  const [result, setResult] = useState<GapAnalysisResponse | null>(() => {
    if (typeof window === 'undefined') return null
    try { const r = sessionStorage.getItem(GAP_STORAGE_KEY); return r ? JSON.parse(r) : null } catch { return null }
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (result) { try { sessionStorage.setItem(GAP_STORAGE_KEY, JSON.stringify(result)) } catch { /* */ } }
  }, [result])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!profile.name) {
      setError('Il nome azienda è obbligatorio')
      return
    }
    if (!profile.employee_count || profile.employee_count < 1) {
      setError('Il numero di dipendenti deve essere almeno 1')
      return
    }
    setError('')
    setLoading(true)
    setResult(null)

    try {
      const res = await api.post<ApiResponse<GapAnalysisResponse>>('/api/v1/gap-analysis', {
        framework,
        company_profile: profile,
      })
      setResult(res.data)
      saveGapScore(framework, res.data.overall_score)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Analysis failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6 max-w-5xl">
      {/* Form */}
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="flex flex-col sm:flex-row gap-3 sm:items-end">
          <div className="flex-1">
            <label htmlFor="ga-framework" className="block text-xs text-slate-500 mb-1.5 uppercase tracking-wider">Framework</label>
            <select
              id="ga-framework"
              value={framework}
              onChange={(e) => setFramework(e.target.value as Framework)}
              className="w-full px-3 py-2.5 bg-surface border border-white/[0.06] rounded-lg text-white focus:outline-none focus:border-accent/40"
            >
              {FRAMEWORKS.map(fw => (
                <option key={fw.value} value={fw.value}>{fw.label}</option>
              ))}
            </select>
          </div>
          <button
            type="submit"
            disabled={loading}
            className="px-6 py-2.5 rounded-lg bg-gradient-to-r from-accent to-accent2 text-white font-medium hover:opacity-90 transition disabled:opacity-50 flex items-center justify-center gap-2 shrink-0"
          >
            {loading ? <Loader2 size={16} className="animate-spin" /> : <ClipboardCheck size={16} />}
            {loading ? 'Analyzing...' : 'Run Analysis'}
          </button>
        </div>

        <CompanyProfileForm value={profile} onChange={setProfile} required />
      </form>

      {error && (
        <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm flex items-center gap-2">
          <AlertTriangle size={16} /> {error}
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center py-16 text-slate-400">
          <Loader2 size={24} className="animate-spin mr-3" />
          <span>Running compliance analysis... This may take 30-60 seconds.</span>
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="space-y-4">
          {/* Score header */}
          <div className="bg-surface border border-white/[0.06] rounded-xl p-6">
            {(() => {
              const confidence = getConfidenceLabel(result.confidence_score)
              const compliance = getComplianceLabel(result.overall_score)
              return (
                <>
                  <div className="flex items-center justify-between mb-4">
                    <div>
                      <h3 className="text-lg font-semibold">{result.framework} - Valutazione Conformità</h3>
                      <div className="flex items-center gap-2 mt-2 flex-wrap">
                        <span className={`text-xs px-2.5 py-1 rounded border font-medium ${confidence.border} ${confidence.bg} ${confidence.color}`}>
                          {confidence.label}
                        </span>
                        <span className="text-xs px-2.5 py-1 rounded border border-amber-400/20 bg-amber-400/10 text-amber-400">
                          Revisione esperto sempre raccomandata
                        </span>
                      </div>
                      <p className="text-[10px] text-slate-500 mt-1">{confidence.sublabel}</p>
                    </div>
                    <div className="text-right">
                      <div className="flex items-center gap-2">
                        <ShieldCheck size={28} className={compliance.color} />
                        <div className={`text-xl font-bold ${compliance.color}`}>
                          {compliance.label}
                        </div>
                      </div>
                      <p className="text-[10px] text-slate-500 mt-1 max-w-[200px]">{compliance.sublabel}</p>
                    </div>
                  </div>

                  {/* Compliance level indicator (blue/neutral, no traffic lights) */}
                  <div className="w-full h-2 bg-surface2 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-1000 ${
                        compliance.level === 'high' ? 'bg-blue-500' :
                        compliance.level === 'medium' ? 'bg-amber-500' : 'bg-orange-500'
                      }`}
                      style={{ width: `${Math.min(result.overall_score, 100)}%` }}
                      role="progressbar"
                      aria-label={compliance.label}
                    />
                  </div>

                  {/* Mandatory AI disclaimer */}
                  <p className="text-[10px] text-slate-500 mt-3 leading-relaxed bg-surface2 rounded-lg px-3 py-2">
                    <strong>Analisi generata da AI</strong> - Questa valutazione rappresenta una stima preliminare basata sulle
                    informazioni fornite e sulla knowledge base normativa di NormaAI. Non costituisce una certificazione di conformità
                    né consulenza legale. Lo stato effettivo di compliance può variare in base a fattori non analizzati.
                    Consultare sempre un professionista qualificato per una valutazione vincolante.
                  </p>
                </>
              )
            })()}

            {/* Status summary */}
            {result.status_summary && (
              <div className="flex flex-wrap gap-4 mt-4">
                {Object.entries(result.status_summary).map(([key, count]) => {
                  const statusKey = key.toUpperCase() as ComplianceStatus
                  const cfg = STATUS_CONFIG[statusKey]
                  if (!cfg) return null
                  return (
                    <div key={key} className="text-center">
                      <div className={`text-lg font-bold ${cfg.color}`}>{count as number}</div>
                      <div className="text-[10px] text-slate-500 uppercase">{cfg.label}</div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          {/* Requirements table */}
          {result.requirements?.length > 0 && (
            <div className="bg-surface border border-white/[0.06] rounded-xl p-5 overflow-x-auto">
              <h3 className="text-xs uppercase tracking-widest text-slate-500 font-semibold mb-4">Requirements Detail</h3>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-slate-500 text-left text-xs">
                    <th className="pb-3 font-medium">Requirement</th>
                    <th className="pb-3 font-medium">Article</th>
                    <th className="pb-3 font-medium">Status</th>
                    <th className="pb-3 font-medium">Priority</th>
                    <th className="pb-3 font-medium">Effort</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.04]">
                  {result.requirements.map((req, i) => {
                    const cfg = STATUS_CONFIG[req.status] || STATUS_CONFIG.NOT_APPLICABLE
                    return (
                      <tr key={i}>
                        <td className="py-2.5 pr-3 max-w-xs">
                          <div className="text-sm">{req.description}</div>
                          {req.gap_description && (
                            <div className="text-xs text-slate-500 mt-0.5">{req.gap_description}</div>
                          )}
                        </td>
                        <td className="py-2.5 text-xs font-mono text-slate-400">{req.article_reference}</td>
                        <td className="py-2.5">
                          <span className={`text-xs px-2 py-0.5 rounded ${cfg.bg} ${cfg.color}`}>{cfg.label}</span>
                        </td>
                        <td className="py-2.5">
                          <span className={`text-xs font-medium ${
                            req.priority === 'P1' ? 'text-red-400' :
                            req.priority === 'P2' ? 'text-yellow-400' :
                            req.priority === 'P3' ? 'text-blue-400' : 'text-slate-500'
                          }`}>{req.priority}</span>
                        </td>
                        <td className="py-2.5 text-xs text-slate-400">{req.remediation_effort}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Recommendations */}
          {result.top_recommendations?.length > 0 && (
            <div className="bg-surface border border-white/[0.06] rounded-xl p-5">
              <h3 className="text-xs uppercase tracking-widest text-slate-500 font-semibold mb-3">Top Recommendations</h3>
              <ol className="space-y-2">
                {result.top_recommendations.map((rec, i) => (
                  <li key={i} className="flex gap-3 text-sm">
                    <span className="text-accent font-bold shrink-0">{i + 1}.</span>
                    <span className="text-slate-300">{rec}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
