'use client'

import { useState, useRef, useEffect } from 'react'
import { api } from '@/lib/api'
import type { MonitorResponse, ApiResponse } from '@/lib/types'
import CompanyProfileForm, { useCompanyProfile } from '@/components/CompanyProfileForm'
import { Bell, Loader2, AlertTriangle, Shield, Clock, Zap } from 'lucide-react'
import { getConfidenceLabel } from '@/lib/confidence-labels'

const URGENCY_CONFIG = {
  CRITICAL: { color: 'text-red-400', bg: 'bg-red-400/10', border: 'border-red-400/20' },
  HIGH: { color: 'text-orange-400', bg: 'bg-orange-400/10', border: 'border-orange-400/20' },
  MEDIUM: { color: 'text-yellow-400', bg: 'bg-yellow-400/10', border: 'border-yellow-400/20' },
  LOW: { color: 'text-blue-400', bg: 'bg-blue-400/10', border: 'border-blue-400/20' },
  INFORMATIONAL: { color: 'text-slate-400', bg: 'bg-slate-400/10', border: 'border-slate-400/20' },
}

const APPLICABILITY_CONFIG = {
  YES: { label: 'Applicable', color: 'text-orange-400', bg: 'bg-orange-400/10' },
  NO: { label: 'Not Applicable', color: 'text-slate-400', bg: 'bg-slate-400/10' },
  CONDITIONAL: { label: 'Conditional', color: 'text-amber-400', bg: 'bg-amber-400/10' },
}

export default function MonitorPage() {
  const [changeText, setChangeText] = useState('')
  const { profile, setProfile } = useCompanyProfile()
  const [result, setResult] = useState<MonitorResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const resultRef = useRef<HTMLDivElement>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!profile.name) { setError('Il nome azienda è obbligatorio'); return }
    if (changeText.length < 10) { setError('Descrivi la modifica normativa (minimo 10 caratteri)'); return }

    setError('')
    setLoading(true)
    setResult(null)

    try {
      const res = await api.post<ApiResponse<MonitorResponse>>('/api/v1/monitor', {
        regulation_change: changeText,
        company_profile: profile,
      })
      setResult(res.data)
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Analysis failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-xs text-slate-500 mb-1.5 uppercase tracking-wider">Regulatory Change</label>
          <textarea
            value={changeText}
            onChange={(e) => { setChangeText(e.target.value); if (error) setError('') }}
            rows={4}
            className="w-full px-4 py-3 bg-surface border border-white/[0.06] rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-accent/40 transition resize-none"
            placeholder="Describe the regulatory change to analyze, e.g.: The Omnibus I Package raised CSRD threshold from 250 to 1000 employees..."
          />
        </div>

        <CompanyProfileForm value={profile} onChange={setProfile} required />

        {error && (
          <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm flex items-center gap-2">
            <AlertTriangle size={16} /> {error}
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="px-6 py-2.5 rounded-lg bg-gradient-to-r from-accent to-accent2 text-white font-medium hover:opacity-90 transition disabled:opacity-50 flex items-center gap-2"
        >
          {loading ? <Loader2 size={16} className="animate-spin" /> : <Bell size={16} />}
          {loading ? 'Analyzing impact...' : 'Analyze Impact'}
        </button>
      </form>

      {loading && (
        <div className="flex items-center justify-center py-16 text-slate-400">
          <Loader2 size={24} className="animate-spin mr-3" />
          <span>Analyzing regulatory impact... This may take 30-60 seconds.</span>
        </div>
      )}

      {result && (
        <div ref={resultRef} className="space-y-4">
          {/* Summary cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {/* Applicability */}
            <div className="bg-surface border border-white/[0.06] rounded-xl p-5">
              <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2">Applicability</div>
              <div className={`text-lg font-bold ${APPLICABILITY_CONFIG[result.applicability]?.color || 'text-white'}`}>
                {APPLICABILITY_CONFIG[result.applicability]?.label || result.applicability}
              </div>
              <p className="text-xs text-slate-400 mt-1">{result.applicability_reason}</p>
            </div>

            {/* Urgency */}
            <div className="bg-surface border border-white/[0.06] rounded-xl p-5">
              <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2">Urgency</div>
              <span className={`inline-block px-3 py-1 rounded-lg text-sm font-semibold ${
                URGENCY_CONFIG[result.urgency]?.bg || ''
              } ${URGENCY_CONFIG[result.urgency]?.color || 'text-white'} border ${
                URGENCY_CONFIG[result.urgency]?.border || ''
              }`}>
                {result.urgency}
              </span>
            </div>

            {/* Deadline */}
            <div className="bg-surface border border-white/[0.06] rounded-xl p-5">
              <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2">Deadline</div>
              <div className="flex items-center gap-2">
                <Clock size={16} className={result.deadline && new Date(result.deadline) < new Date() ? 'text-blue-400' : 'text-slate-400'} />
                <span className={`text-sm ${result.deadline && new Date(result.deadline) < new Date() ? 'text-blue-400' : ''}`}>
                  {result.deadline || 'Not specified'}
                </span>
                {result.deadline && new Date(result.deadline) < new Date() && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-500/10 border border-blue-500/20 text-blue-400 font-semibold">IN VIGORE</span>
                )}
              </div>
              {result.deadline_is_confirmed !== undefined && (
                <div className="text-[10px] text-slate-500 mt-1">
                  {result.deadline_is_confirmed ? 'Confirmed' : 'Estimated'}
                </div>
              )}
            </div>
          </div>

          {/* Impact summary */}
          <div className="bg-surface border border-white/[0.06] rounded-xl p-5">
            <h3 className="text-xs uppercase tracking-widest text-slate-500 font-semibold mb-3 flex items-center gap-2">
              <Zap size={14} /> Impact Summary
            </h3>
            <p className="text-sm text-slate-300 leading-relaxed">{result.impact_summary}</p>
          </div>

          {/* Required actions */}
          {result.required_actions?.length > 0 && (
            <div className="bg-surface border border-white/[0.06] rounded-xl p-5">
              <h3 className="text-xs uppercase tracking-widest text-slate-500 font-semibold mb-3">Required Actions</h3>
              <ol className="space-y-2">
                {result.required_actions.map((action, i) => (
                  <li key={i} className="flex gap-3 text-sm">
                    <span className="text-accent font-bold shrink-0">{i + 1}.</span>
                    <span className="text-slate-300">{action}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}

          {/* Cross-framework impacts */}
          {result.cross_framework_impacts?.length > 0 && (
            <div className="bg-surface border border-white/[0.06] rounded-xl p-5">
              <h3 className="text-xs uppercase tracking-widest text-slate-500 font-semibold mb-3 flex items-center gap-2">
                <Shield size={14} /> Cross-Framework Impacts
              </h3>
              <div className="space-y-1">
                {result.cross_framework_impacts.map((impact, i) => (
                  <div key={i} className="text-sm text-slate-300 bg-surface2 rounded-lg px-3 py-2">
                    {impact}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Confidence + AI disclosure */}
          <div className="flex items-center gap-2 text-xs text-slate-500 flex-wrap">
            {(() => { const conf = getConfidenceLabel(result.confidence_score); return (
              <span className={`px-2 py-0.5 rounded border font-medium ${conf.border} ${conf.bg} ${conf.color}`}>
                {conf.label}
              </span>
            ); })()}
            <span className="px-2 py-0.5 rounded border border-amber-400/20 bg-amber-400/10 text-amber-400">
              {result.requires_expert_review ? 'Revisione esperto consigliata' : 'Verifica sempre raccomandata'}
            </span>
          </div>
          <p className="text-[9px] text-slate-600 italic">
            Analisi generata da AI — verificare con fonti ufficiali prima di decisioni vincolanti.
          </p>
        </div>
      )}
    </div>
  )
}
