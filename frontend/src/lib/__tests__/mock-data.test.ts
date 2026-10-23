import { describe, it, expect } from 'vitest'
import {
  DEMO_STATS,
  DEMO_USER,
  DEMO_CLIENTS,
  getMockGapAnalysis,
  getMockMonitorResponse,
  mockDelay,
} from '../mock-data'

const BACKEND_FRAMEWORKS = ['CSRD', 'CSDDD', 'AI_ACT', 'DORA', 'NIS2', 'TAXONOMY', 'GDPR', 'CRA']

describe('DEMO_STATS', () => {
  it('has correct structure', () => {
    expect(DEMO_STATS.status).toBe('healthy')
    expect(DEMO_STATS.version).toBeDefined()
    expect(DEMO_STATS.environment).toBe('demo')
    expect(typeof DEMO_STATS.qdrant_available).toBe('boolean')
    expect(typeof DEMO_STATS.llm_available).toBe('boolean')
    expect(DEMO_STATS.metrics).toBeDefined()
    expect(typeof DEMO_STATS.metrics.total_requests).toBe('number')
    expect(typeof DEMO_STATS.metrics.error_count).toBe('number')
  })

  it('has valid endpoint metrics', () => {
    const endpoints = DEMO_STATS.metrics.endpoints
    expect(Object.keys(endpoints).length).toBeGreaterThan(0)
    for (const val of Object.values(endpoints)) {
      expect(val.count).toBeGreaterThan(0)
      expect(val.avg_latency_ms).toBeGreaterThan(0)
      expect(val.max_latency_ms).toBeGreaterThanOrEqual(val.avg_latency_ms)
    }
  })
})

describe('DEMO_USER', () => {
  it('is an admin so the demo shows every surface', () => {
    expect(DEMO_USER.role).toBe('admin')
    expect(DEMO_USER.email).toContain('@')
  })
})

describe('DEMO_CLIENTS', () => {
  it('has unique ids and the fields the clients API returns', () => {
    const ids = DEMO_CLIENTS.map((c) => c.id)
    expect(new Set(ids).size).toBe(ids.length)
    for (const client of DEMO_CLIENTS) {
      expect(client.name.length).toBeGreaterThan(0)
      expect(typeof client.employee_count).toBe('number')
      expect(typeof client.revenue_eur).toBe('number')
      expect(Array.isArray(client.jurisdictions)).toBe(true)
      expect(Array.isArray(client.applicable_frameworks)).toBe(true)
      expect(new Date(client.created_at).getTime()).not.toBeNaN()
      expect(new Date(client.updated_at).getTime()).not.toBeNaN()
    }
  })

  it('uses the framework keys the backend accepts', () => {
    for (const client of DEMO_CLIENTS) {
      for (const fw of client.applicable_frameworks) {
        expect(BACKEND_FRAMEWORKS).toContain(fw)
      }
    }
  })
})

describe('getMockGapAnalysis', () => {
  it('returns a consistent status summary for every framework', () => {
    for (const fw of BACKEND_FRAMEWORKS) {
      const result = getMockGapAnalysis(fw)
      expect(result.framework).toBe(fw)
      expect(result.requirements.length).toBeGreaterThan(0)
      expect(result.overall_score).toBeGreaterThanOrEqual(0)
      expect(result.overall_score).toBeLessThanOrEqual(100)
      const counted = Object.values(result.status_summary).reduce((a, b) => a + b, 0)
      expect(counted).toBe(result.requirements.length)
      expect(result.top_recommendations.length).toBeGreaterThan(0)
    }
  })

  it('falls back to sample data for an unknown framework', () => {
    const result = getMockGapAnalysis('UNKNOWN')
    expect(result.requirements.length).toBeGreaterThan(0)
  })
})

describe('getMockMonitorResponse', () => {
  it('returns an applicability and required actions', () => {
    const result = getMockMonitorResponse('Modifica delle soglie CSRD')
    expect(['YES', 'NO', 'CONDITIONAL']).toContain(result.applicability)
    expect(Array.isArray(result.required_actions)).toBe(true)
  })
})

describe('mockDelay', () => {
  it('resolves after the given time', async () => {
    const start = Date.now()
    await mockDelay(10)
    expect(Date.now() - start).toBeGreaterThanOrEqual(5)
  })
})
