import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest'
import { api } from '../api'
import { checkHref, normaliseAlerts, normaliseSummary } from '@/components/monitoraggio/AlertsTab'
import { normaliseClients } from '@/components/ambito/clients'
import { DEMO_CORPUS_AS_OF } from '../mock-data'
import type { ApiResponse, GapAnalysisResponse, MonitorResponse } from '../types'
import type { DemoQAResponse } from '../demo/types'

/**
 * What a visitor of the demo gets, through the real API client: demo mode
 * is on and every call goes through api.get / api.post, with the shapes the
 * pages read.
 */
vi.mock('../auth', () => ({
  isDemoMode: () => true,
  getAccessToken: () => 'demo.jwt.token',
  getRefreshToken: () => null,
  setTokens: vi.fn(),
  clearTokens: vi.fn(),
  isTokenExpired: () => false,
}))

const ZETA = {
  name: 'Zeta Componenti S.p.A.',
  sector: "Componentistica per l'automotive",
  employee_count: 1650,
  revenue_eur: 520_000_000,
  jurisdictions: ['IT'],
  applicable_frameworks: ['CSRD'],
  existing_documents: '',
}

/** The demo client waits on a timer before answering: run the timers, then read the answer. */
async function settled<T>(call: Promise<T>): Promise<T> {
  await vi.advanceTimersByTimeAsync(5000)
  return call
}

describe('demo mode through the API client', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    document.cookie = 'normaai.locale=; path=/; max-age=0'
  })

  it('lists the clients of the firm', async () => {
    const clients = normaliseClients(await settled(api.get<unknown>('/api/v1/clients')))
    expect(clients).toHaveLength(6)
    expect(clients.every((c) => typeof c.employee_count === 'number' && typeof c.revenue_eur === 'number')).toBe(true)
  })

  it('lists the alerts in the language of the interface', async () => {
    const italian = normaliseAlerts(await settled(api.get<unknown>('/api/v1/alerts?limit=50&offset=0')))
    expect(italian).toHaveLength(7)
    expect(italian[0].title).toContain('marcatura')
    // The alert of the re-check opens the check of the document to review.
    const review = italian.find((a) => a.document_check_id)
    expect(review && checkHref(review)).toBe('/app/controlla/demo-doc-csddd')

    document.cookie = 'normaai.locale=en; path=/'
    const english = normaliseAlerts(await settled(api.get<unknown>('/api/v1/alerts?limit=50&offset=0')))
    expect(english[0].title).toContain('marking')

    const summary = normaliseSummary(await settled(api.get<unknown>('/api/v1/alerts/summary')))
    expect(summary).toEqual({ total: 7, unread: 5 })
  })

  it('answers a question with sources and the demo corpus date', async () => {
    const res = await settled(
      api.post<ApiResponse<DemoQAResponse>>('/api/v1/qa', {
        question: 'Does a chatbot on the company website have to say that it is an AI?',
        language: 'en',
      }),
    )
    expect(res.data.answer.startsWith('Yes.')).toBe(true)
    expect(res.data.citations.length).toBeGreaterThan(0)
    expect(res.data.citations.every((c) => c.verified)).toBe(true)
    expect(res.metadata?.corpus_as_of).toBe(DEMO_CORPUS_AS_OF)
  })

  it('runs a gap analysis that never treats a large client as out of scope', async () => {
    const res = await settled(
      api.post<ApiResponse<GapAnalysisResponse>>('/api/v1/gap-analysis', { framework: 'CSRD', company_profile: ZETA }),
    )
    expect(res.data.framework).toBe('CSRD')
    // "COMPLIANT" (scope checked) once the client passes the profile on, "IN_EVOLUTION" (to be checked) until then.
    expect(['COMPLIANT', 'IN_EVOLUTION']).toContain(res.data.requirements[0].status)
    expect(res.data.requirements[0].gap_description).toMatch(/1\.000 dipendenti|soglie/)
    expect(res.data.top_recommendations.length).toBeGreaterThan(0)
  })

  it('analyses a change without claiming to have read it', async () => {
    const res = await settled(
      api.post<ApiResponse<MonitorResponse>>('/api/v1/monitor', {
        regulation_change: "L'Omnibus I (Direttiva (UE) 2026/470) ha alzato le soglie CSRD.",
        company_profile: ZETA,
      }),
    )
    // "YES" once the client passes the profile on, "CONDITIONAL" until then: never "NO" for this client.
    expect(['YES', 'CONDITIONAL']).toContain(res.data.applicability)
    expect(res.data.impact_summary).toContain('Esempio della demo')
    expect(res.data.citations.length).toBeGreaterThan(0)
  })

  it('reports no server status', async () => {
    const stats = await settled(api.get<{ status: string; qdrant_available: boolean; llm_available: boolean }>('/api/v1/stats'))
    expect(stats.status).toBe('demo')
    expect(stats.qdrant_available).toBe(false)
    expect(stats.llm_available).toBe(false)
  })
})
