import { describe, it, expect } from 'vitest'
import {
  DEMO_STATS,
  KNOWLEDGE_BASE_META,
  DEMO_ROLES,
  DEMO_AUDIT_EVENTS,
} from '../mock-data'

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
    for (const [key, val] of Object.entries(endpoints)) {
      expect(val.count).toBeGreaterThan(0)
      expect(val.avg_latency_ms).toBeGreaterThan(0)
      expect(val.max_latency_ms).toBeGreaterThanOrEqual(val.avg_latency_ms)
    }
  })
})

describe('KNOWLEDGE_BASE_META', () => {
  it('has a valid date string', () => {
    const d = new Date(KNOWLEDGE_BASE_META.updated_at)
    expect(d.getTime()).not.toBeNaN()
  })

  it('has positive counts', () => {
    expect(KNOWLEDGE_BASE_META.chunks_count).toBeGreaterThan(0)
    expect(KNOWLEDGE_BASE_META.frameworks_count).toBeGreaterThan(0)
  })

  it('frameworks count matches array length', () => {
    expect(KNOWLEDGE_BASE_META.frameworks.length).toBe(KNOWLEDGE_BASE_META.frameworks_count)
  })

  it('contains all expected EU frameworks', () => {
    expect(KNOWLEDGE_BASE_META.frameworks).toContain('CSRD')
    expect(KNOWLEDGE_BASE_META.frameworks).toContain('GDPR')
    expect(KNOWLEDGE_BASE_META.frameworks).toContain('DORA')
  })
})

describe('DEMO_ROLES', () => {
  it('has unique IDs', () => {
    const ids = DEMO_ROLES.map(r => r.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('each role has valid permissions array', () => {
    for (const role of DEMO_ROLES) {
      expect(Array.isArray(role.permissions)).toBe(true)
      expect(role.permissions.length).toBeGreaterThan(0)
      for (const perm of role.permissions) {
        expect(typeof perm).toBe('string')
        expect(perm).toMatch(/^[a-z_]+\.[a-z_]+$/)
      }
    }
  })

  it('admin role has the most permissions', () => {
    const admin = DEMO_ROLES.find(r => r.name === 'Administrator')
    expect(admin).toBeDefined()
    for (const role of DEMO_ROLES) {
      expect(admin!.permissions.length).toBeGreaterThanOrEqual(role.permissions.length)
    }
  })
})

describe('DEMO_AUDIT_EVENTS', () => {
  it('has events', () => {
    expect(DEMO_AUDIT_EVENTS.length).toBeGreaterThan(0)
  })

  it('all events have valid timestamps', () => {
    for (const event of DEMO_AUDIT_EVENTS) {
      const d = new Date(event.timestamp)
      expect(d.getTime()).not.toBeNaN()
    }
  })

  it('all events have required fields', () => {
    for (const event of DEMO_AUDIT_EVENTS) {
      expect(event.id).toBeDefined()
      expect(event.user_id).toBeDefined()
      expect(event.user_name).toBeDefined()
      expect(event.action).toBeDefined()
      expect(event.resource_type).toBeDefined()
      expect(event.details).toBeDefined()
      expect(event.ip_address).toBeDefined()
    }
  })

  it('events have unique IDs', () => {
    const ids = DEMO_AUDIT_EVENTS.map(e => e.id)
    expect(new Set(ids).size).toBe(ids.length)
  })
})
