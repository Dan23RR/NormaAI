import { api } from '@/lib/api'
import type { ApiResponse, CompanyProfile, GapAnalysisResponse } from '@/lib/types'

/**
 * Reports against src/api/routers/reports.py.
 *
 * - POST /api/v1/reports/gap-analysis       {framework, company_profile}  -> the PDF itself (streamed)
 * - POST /api/v1/reports/executive-summary  {frameworks[], company_profile} -> the PDF itself
 * - GET  /api/v1/reports/history            -> {status, data: ReportHistoryItem[], pagination}
 *
 * There is no route to download a report generated earlier: the PDF exists
 * only in the response of the generation call. In demo mode the api client
 * reads the history from sessionStorage (normaai_demo_reports) and the PDF
 * routes are not available, so the analysis is shown on screen instead.
 */

export type ReportType = 'gap_analysis' | 'executive_summary'

export const REPORT_TYPE_LABEL: Record<ReportType, string> = {
  gap_analysis: 'Gap analysis',
  executive_summary: 'Sintesi direzionale',
}

export interface ReportHistoryItem {
  id: string
  report_type: string
  framework: string | null
  frameworks: string[] | null
  company_name: string
  generated_at: string
  overall_score: number | null
}

export function normalizeHistory(res: unknown): ReportHistoryItem[] {
  const list = Array.isArray(res) ? res : (res as { data?: unknown } | null)?.data
  if (!Array.isArray(list)) return []
  return list.map((raw) => {
    const r = (raw ?? {}) as Record<string, unknown>
    return {
      id: String(r.report_id ?? r.id ?? ''),
      report_type: typeof r.report_type === 'string' ? r.report_type : 'gap_analysis',
      framework: typeof r.framework === 'string' ? r.framework : null,
      frameworks: Array.isArray(r.frameworks) ? (r.frameworks as string[]) : null,
      company_name: typeof r.company_name === 'string' ? r.company_name : '',
      generated_at: typeof r.generated_at === 'string' ? r.generated_at : typeof r.created_at === 'string' ? r.created_at : '',
      overall_score: typeof r.overall_score === 'number' ? r.overall_score : null,
    }
  })
}

export async function fetchReportHistory(): Promise<ReportHistoryItem[]> {
  return normalizeHistory(await api.get<unknown>('/api/v1/reports/history?limit=50'))
}

const DEMO_REPORTS_KEY = 'normaai_demo_reports'

/** The demo history lives in sessionStorage, in the same shape the backend returns. */
export function saveDemoReport(item: ReportHistoryItem) {
  try {
    const stored = sessionStorage.getItem(DEMO_REPORTS_KEY)
    const list: Array<Record<string, unknown>> = stored ? JSON.parse(stored) : []
    list.unshift({
      report_id: item.id,
      report_type: item.report_type,
      framework: item.framework,
      frameworks: item.frameworks,
      company_name: item.company_name,
      generated_at: item.generated_at,
      overall_score: item.overall_score,
    })
    sessionStorage.setItem(DEMO_REPORTS_KEY, JSON.stringify(list.slice(0, 20)))
  } catch {
    /* the history stays in memory for this page only */
  }
}

export function filenameFromDisposition(header: string | null): string | null {
  if (!header) return null
  const utf8 = header.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8) {
    try {
      return decodeURIComponent(utf8[1].trim())
    } catch {
      /* fall through */
    }
  }
  const plain = header.match(/filename="?([^";]+)"?/i)
  return plain ? plain[1].trim() : null
}

export async function generatePdf(
  type: ReportType,
  frameworks: string[],
  profile: CompanyProfile,
): Promise<{ blob: Blob; filename: string }> {
  const endpoint = type === 'gap_analysis' ? '/api/v1/reports/gap-analysis' : '/api/v1/reports/executive-summary'
  const body =
    type === 'gap_analysis'
      ? { framework: frameworks[0], company_profile: profile }
      : { frameworks, company_profile: profile }
  const res = await api.fetchBlob(endpoint, { method: 'POST', body: JSON.stringify(body) })
  const safeName = profile.name.replace(/\s+/g, '_').slice(0, 30)
  const fallback =
    type === 'gap_analysis'
      ? `NormaAI_${frameworks[0]}_Gap_Report_${safeName}.pdf`
      : `NormaAI_Executive_Summary_${safeName}.pdf`
  return { blob: await res.blob(), filename: filenameFromDisposition(res.headers.get('Content-Disposition')) ?? fallback }
}

/** Demo: the analysis runs on sample data and is shown on screen, no PDF. */
export async function runDemoAnalyses(frameworks: string[], profile: CompanyProfile): Promise<GapAnalysisResponse[]> {
  const results = await Promise.all(
    frameworks.map((framework) =>
      api.post<ApiResponse<GapAnalysisResponse>>('/api/v1/gap-analysis', { framework, company_profile: profile }),
    ),
  )
  return results.map((r) => r.data)
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
