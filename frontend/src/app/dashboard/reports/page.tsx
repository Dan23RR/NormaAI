'use client'

import { useState, useEffect, useCallback } from 'react'
import { api } from '@/lib/api'
import { isDemoMode } from '@/lib/auth'
import { getMockGapAnalysis, mockDelay } from '@/lib/mock-data'
import type { Framework, CompanyProfile } from '@/lib/types'
import { FRAMEWORKS } from '@/lib/types'
import CompanyProfileForm, { useCompanyProfile } from '@/components/CompanyProfileForm'
import { FileText, Download, Loader2, ClipboardCheck, BarChart3, AlertTriangle, Clock, CheckCircle, FileCheck } from 'lucide-react'

type ReportType = 'gap-analysis' | 'executive-summary' | 'audit-pack'
const DEMO_REPORTS_KEY = 'normaai_demo_reports'

function saveDemoReport(item: ReportHistoryItem) {
  try {
    const stored = sessionStorage.getItem(DEMO_REPORTS_KEY)
    const list: ReportHistoryItem[] = stored ? JSON.parse(stored) : []
    list.unshift(item)
    sessionStorage.setItem(DEMO_REPORTS_KEY, JSON.stringify(list.slice(0, 20)))
  } catch { /* ignore */ }
}

interface ReportHistoryItem {
  id: string
  report_type: string
  framework: string | null
  frameworks: string[] | null
  created_at: string
  filename: string
}

export default function ReportsPage() {
  const [reportType, setReportType] = useState<ReportType>('gap-analysis')
  const [framework, setFramework] = useState<Framework>('CSRD')
  const [selectedFrameworks, setSelectedFrameworks] = useState<Framework[]>(['CSRD'])
  const { profile, setProfile } = useCompanyProfile()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [history, setHistory] = useState<ReportHistoryItem[]>([])
  const [historyLoading, setHistoryLoading] = useState(true)

  const fetchHistory = useCallback(async () => {
    try {
      const res = await api.get<{ data: ReportHistoryItem[] }>('/api/v1/reports/history')
      setHistory(Array.isArray(res) ? res : res.data ?? [])
    } catch {
      // History may not be available yet
      setHistory([])
    } finally {
      setHistoryLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchHistory()
  }, [fetchHistory])

  const toggleFramework = (fw: Framework) => {
    setSelectedFrameworks(prev =>
      prev.includes(fw) ? prev.filter(f => f !== fw) : [...prev, fw]
    )
  }

  const downloadBlob = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!profile.name) {
      setError('Il nome azienda è obbligatorio')
      return
    }
    if ((reportType === 'executive-summary' || reportType === 'audit-pack') && selectedFrameworks.length === 0) {
      setError('Seleziona almeno un framework per l\'Executive Summary')
      return
    }

    setError('')
    setSuccess('')
    setLoading(true)

    // Demo mode: generate client-side HTML report
    if (isDemoMode()) {
      await mockDelay(2000)
      const frameworks = reportType === 'gap-analysis' ? [framework] : reportType === 'audit-pack' ? selectedFrameworks : selectedFrameworks
      const analyses = frameworks.map(fw => getMockGapAnalysis(fw))

      const html = `<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>NormaAI Report - ${profile.name}</title>
<style>body{font-family:system-ui,sans-serif;max-width:900px;margin:0 auto;padding:40px;color:#1a1a2e}
h1{color:#6366f1;border-bottom:2px solid #6366f1;padding-bottom:8px}
h2{color:#334155;margin-top:32px}
table{width:100%;border-collapse:collapse;margin:16px 0}
th,td{border:1px solid #e2e8f0;padding:8px 12px;text-align:left;font-size:13px}
th{background:#f8fafc;font-weight:600}
.score{font-size:20px;font-weight:700;color:#3b82f6}
.badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600}
.compliant{background:#dbeafe;color:#1d4ed8}
.partial{background:#fef3c7;color:#92400e}
.non-compliant{background:#ffedd5;color:#c2410c}
.na{background:#f1f5f9;color:#64748b}
.ai-badge{background:#eff6ff;color:#2563eb;border:1px solid #bfdbfe;padding:4px 10px;border-radius:4px;font-size:10px;font-weight:600;display:inline-block;margin-right:8px}
.disclaimer{background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:10px 14px;font-size:10px;color:#64748b;margin-top:12px;line-height:1.5}
.footer{margin-top:40px;padding-top:16px;border-top:1px solid #e2e8f0;font-size:11px;color:#94a3b8}
</style></head><body>
<h1>NormaAI — ${reportType === 'audit-pack' ? 'Audit Evidence Pack' : reportType === 'executive-summary' ? 'Executive Summary' : 'Gap Analysis Report'}</h1>
<p><strong>Company:</strong> ${profile.name} | <strong>Sector:</strong> ${profile.sector} | <strong>Employees:</strong> ${profile.employee_count.toLocaleString()} | <strong>Revenue:</strong> &euro;${profile.revenue_eur.toLocaleString()}</p>
<p><strong>Jurisdictions:</strong> ${profile.jurisdictions.join(', ')} | <strong>Generated:</strong> ${new Date().toLocaleDateString('en-GB')}</p>
${analyses.map(a => `
<h2>${a.framework} Compliance Analysis</h2>
<p><span class="ai-badge">AI Act Art. 50 — Analisi generata da AI</span></p>
<p>Livello di conformità: <span class="score">${a.overall_score >= 70 ? 'Buon livello di conformità' : a.overall_score >= 40 ? 'Conformità parziale' : 'Gap significativi rilevati'}</span></p>
<p style="font-size:11px;color:#64748b">Affidabilità analisi: ${a.confidence_score >= 0.85 ? 'Alta — basata su fonti normative dirette' : a.confidence_score >= 0.65 ? 'Media — verifica raccomandata' : 'Preliminare — revisione esperto necessaria'}</p>
<div class="disclaimer"><strong>Nota legale:</strong> Questa valutazione è una stima preliminare generata da intelligenza artificiale. Non costituisce consulenza legale né certificazione di conformità. Consultare un professionista qualificato per valutazioni vincolanti.</div>
<table><thead><tr><th>Requirement</th><th>Article</th><th>Status</th><th>Priority</th><th>Gap</th></tr></thead><tbody>
${a.requirements.map(r => `<tr><td>${r.description}</td><td>${r.article_reference}</td><td><span class="badge ${r.status === 'COMPLIANT' ? 'compliant' : r.status === 'PARTIALLY_COMPLIANT' ? 'partial' : r.status === 'NON_COMPLIANT' ? 'non-compliant' : 'na'}">${r.status.replace(/_/g, ' ')}</span></td><td>${r.priority}</td><td>${r.gap_description || '&mdash;'}</td></tr>`).join('')}
</tbody></table>
<h3>Top Recommendations</h3><ol>${a.top_recommendations.map(r => `<li>${r}</li>`).join('')}</ol>
`).join('')}
<div class="footer"><strong>Report generato automaticamente da NormaAI (sistema di intelligenza artificiale)</strong> in data ${new Date().toLocaleDateString('it-IT')}. Questo documento non sostituisce una consulenza professionale. Le analisi sono stime basate su AI e possono contenere imprecisioni. &mdash; NormaAI v0.3 (Demo Mode)</div>
</body></html>`

      const blob = new Blob([html], { type: 'text/html' })
      const filename = reportType === 'gap-analysis'
        ? `gap-analysis-${framework}-${Date.now()}.html`
        : reportType === 'audit-pack'
        ? `audit-pack-${Date.now()}.html`
        : `executive-summary-${Date.now()}.html`
      downloadBlob(blob, filename)

      // Persist to demo history
      const historyItem: ReportHistoryItem = {
        id: `demo-${Date.now()}`,
        report_type: reportType,
        framework: reportType === 'gap-analysis' ? framework : null,
        frameworks: reportType !== 'gap-analysis' ? [...selectedFrameworks] : null,
        created_at: new Date().toISOString(),
        filename,
      }
      saveDemoReport(historyItem)
      fetchHistory() // refresh history list

      setSuccess(`Report downloaded: ${filename}`)
      setLoading(false)
      return
    }

    try {
      const endpoint = reportType === 'gap-analysis'
        ? '/api/v1/reports/gap-analysis'
        : '/api/v1/reports/executive-summary'

      const body = reportType === 'gap-analysis'
        ? { framework, company_profile: profile }
        : { frameworks: selectedFrameworks, company_profile: profile }

      const res = await api.fetchBlob(endpoint, {
        method: 'POST',
        body: JSON.stringify(body),
      })

      const blob = await res.blob()
      const filename = reportType === 'gap-analysis'
        ? `gap-analysis-${framework}-${Date.now()}.pdf`
        : `executive-summary-${Date.now()}.pdf`

      downloadBlob(blob, filename)
      setSuccess(`Report downloaded: ${filename}`)
      fetchHistory()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Report generation failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6 max-w-5xl">
      {/* Report type selector */}
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => setReportType('gap-analysis')}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium border transition ${
            reportType === 'gap-analysis'
              ? 'border-accent/40 bg-accent/10 text-accent'
              : 'border-white/[0.06] text-slate-400 hover:text-slate-200 hover:border-white/10'
          }`}
        >
          <ClipboardCheck size={16} />
          Gap Analysis Report
        </button>
        <button
          type="button"
          onClick={() => setReportType('executive-summary')}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium border transition ${
            reportType === 'executive-summary'
              ? 'border-accent/40 bg-accent/10 text-accent'
              : 'border-white/[0.06] text-slate-400 hover:text-slate-200 hover:border-white/10'
          }`}
        >
          <BarChart3 size={16} />
          Executive Summary
        </button>
        <button
          type="button"
          onClick={() => setReportType('audit-pack')}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium border transition ${
            reportType === 'audit-pack'
              ? 'border-accent/40 bg-accent/10 text-accent'
              : 'border-white/[0.06] text-slate-400 hover:text-slate-200 hover:border-white/10'
          }`}
        >
          <FileCheck size={16} />
          Audit Pack
        </button>
      </div>

      {/* Form */}
      <form onSubmit={handleGenerate} className="space-y-4">
        {/* Framework selection */}
        {reportType === 'gap-analysis' ? (
          <div>
            <label htmlFor="rpt-framework" className="block text-xs text-slate-500 mb-1.5 uppercase tracking-wider">
              Framework
            </label>
            <select
              id="rpt-framework"
              value={framework}
              onChange={(e) => setFramework(e.target.value as Framework)}
              className="w-full px-3 py-2.5 bg-surface border border-white/[0.06] rounded-lg text-white focus:outline-none focus:border-accent/40"
            >
              {FRAMEWORKS.map(fw => (
                <option key={fw.value} value={fw.value}>{fw.label}</option>
              ))}
            </select>
          </div>
        ) : (
          <div>
            <label className="block text-xs text-slate-500 mb-2 uppercase tracking-wider">
              Frameworks (select multiple)
            </label>
            <div className="flex flex-wrap gap-2" role="group" aria-label="Framework selection">
              {FRAMEWORKS.map(fw => {
                const selected = selectedFrameworks.includes(fw.value)
                return (
                  <button
                    key={fw.value}
                    type="button"
                    onClick={() => toggleFramework(fw.value)}
                    className={`px-3 py-1.5 rounded-md text-xs font-medium border transition ${
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
          </div>
        )}

        {/* Company profile */}
        <CompanyProfileForm value={profile} onChange={setProfile} required />

        {/* Generate button */}
        <button
          type="submit"
          disabled={loading}
          className="px-6 py-2.5 rounded-lg bg-gradient-to-r from-accent to-accent2 text-white font-medium hover:opacity-90 transition disabled:opacity-50 flex items-center justify-center gap-2"
        >
          {loading ? <Loader2 size={16} className="animate-spin" /> : <FileText size={16} />}
          {loading ? 'Generating...' : 'Generate & Download PDF'}
        </button>
      </form>

      {/* Messages */}
      {error && (
        <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm flex items-center gap-2">
          <AlertTriangle size={16} /> {error}
        </div>
      )}

      {success && (
        <div className="p-4 bg-green-500/10 border border-green-500/20 rounded-lg text-green-400 text-sm flex items-center gap-3">
          <CheckCircle size={20} className="shrink-0" />
          <div>
            <div className="font-medium">{success}</div>
            <div className="text-xs text-green-400/70 mt-0.5">Check your downloads folder. Report also saved to history below.</div>
          </div>
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center py-16 text-slate-400">
          <Loader2 size={24} className="animate-spin mr-3" />
          <span>Generating report... This may take 30-60 seconds.</span>
        </div>
      )}

      {/* Report History */}
      <div className="bg-surface border border-white/[0.06] rounded-xl p-5">
        <h3 className="text-xs uppercase tracking-widest text-slate-500 font-semibold mb-4 flex items-center gap-2">
          <Clock size={14} />
          Recent Reports
        </h3>

        {historyLoading ? (
          <div className="space-y-2">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="h-10 bg-surface2 rounded animate-pulse" />
            ))}
          </div>
        ) : history.length === 0 ? (
          <div className="py-8 text-center text-slate-500 text-sm">
            <FileText size={32} className="mx-auto mb-2 opacity-40" />
            No reports generated yet. Generate your first report above.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-500 text-left text-xs">
                <th className="pb-3 font-medium">Report</th>
                <th className="pb-3 font-medium">Framework(s)</th>
                <th className="pb-3 font-medium">Date</th>
                <th className="pb-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.04]">
              {history.map(item => (
                <tr key={item.id}>
                  <td className="py-2.5 pr-3">
                    <div className="flex items-center gap-2">
                      <FileText size={14} className="text-accent shrink-0" />
                      <span className="text-slate-300">{item.filename || item.report_type}</span>
                    </div>
                  </td>
                  <td className="py-2.5">
                    <div className="flex flex-wrap gap-1">
                      {(item.frameworks ?? (item.framework ? [item.framework] : [])).map(fw => {
                        const fwDef = FRAMEWORKS.find(f => f.value === fw)
                        return (
                          <span
                            key={fw}
                            className="text-[10px] px-1.5 py-0.5 rounded border border-white/[0.08] font-medium"
                            style={{ color: fwDef?.color ?? '#94a3b8' }}
                          >
                            {fw}
                          </span>
                        )
                      })}
                    </div>
                  </td>
                  <td className="py-2.5 text-xs text-slate-400">
                    {new Date(item.created_at).toLocaleDateString()}
                  </td>
                  <td className="py-2.5 text-right">
                    <button
                      type="button"
                      onClick={async () => {
                        try {
                          const res = await api.fetchBlob(`/api/v1/reports/${item.id}/download`)
                          const blob = await res.blob()
                          downloadBlob(blob, item.filename || `report-${item.id}.pdf`)
                        } catch (err) {
                          setError(err instanceof Error ? err.message : 'Download failed')
                        }
                      }}
                      className="text-accent hover:text-accent/80 transition p-1"
                      title="Download"
                    >
                      <Download size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
