import { describe, expect, it } from 'vitest'
import { LEAD_ROLES, checkLead, clientIp, createRateLimiter, plainText } from '../leads'

describe('checkLead', () => {
  const lead = (fields: Record<string, unknown>) => checkLead({ email: 'ada@example.test', ...fields })

  it('accepts every source the three forms send', () => {
    const sources = [
      'codex_download',
      'aiact_checker:out',
      'aiact_checker:in:chat',
      'aiact_checker:in:chat+gen',
      'aiact_checker:in:chat+gen+emo+deep',
      'scope_checker:in',
      'scope_checker:filo',
      'scope_checker:out',
    ]
    for (const source of sources) expect(lead({ source }).ok, source).toBe(true)
  })

  it('reads a missing source as the Codex form', () => {
    const checked = lead({})
    expect(checked.ok && checked.lead.source).toBe('codex_download')
  })

  it('refuses any other source', () => {
    for (const source of ['newsletter', 'aiact_checker:maybe', 'scope_checker:in:x', 'codex_download\n', 7]) {
      expect(lead({ source })).toEqual({ ok: false, field: 'source' })
    }
  })

  it('keeps the roles the forms send and drops any other', () => {
    for (const role of LEAD_ROLES) {
      const checked = lead({ role, marketing_consent: true })
      expect(checked.ok && checked.lead.role).toBe(role)
    }
    const other = lead({ role: 'Amministratore delegato', marketing_consent: true })
    expect(other.ok && other.lead.role).toBeNull()
  })

  it('keeps nothing that identifies a Codex download without consent, and needs no address for it', () => {
    expect(lead({ org_name: 'Rossi', role: 'Altro', lead_ref: 'p07' })).toEqual({
      ok: true,
      lead: {
        email: null,
        orgName: null,
        role: null,
        source: 'codex_download',
        leadRef: null,
        marketingConsent: false,
        wantsReply: false,
      },
    })
    expect(checkLead({ source: 'codex_download' }).ok).toBe(true)
  })

  it('needs an address with consent, and for a checker, which asks for a reply', () => {
    expect(checkLead({ marketing_consent: true })).toEqual({ ok: false, field: 'email' })
    expect(checkLead({ source: 'aiact_checker:out' })).toEqual({ ok: false, field: 'email' })
    const reply = lead({ source: 'aiact_checker:out' })
    expect(reply.ok && reply.lead).toMatchObject({ email: 'ada@example.test', marketingConsent: false, wantsReply: true })
  })

  it('refuses a body that is not an object', () => {
    for (const body of [null, 'ada@example.test', ['ada@example.test'], 3]) {
      expect(checkLead(body)).toEqual({ ok: false, field: 'body' })
    }
  })
})

describe('plainText', () => {
  it('turns control characters and line separators into single spaces and cuts the length', () => {
    expect(plainText(' Rossi\r\n\tS.p.A.\u2028 ', 200)).toBe('Rossi S.p.A.')
    expect(plainText('x'.repeat(300), 200)).toHaveLength(200)
    expect(plainText(42, 200)).toBe('')
  })
})

describe('clientIp', () => {
  it('prefers the headers the platform writes, then the first X-Forwarded-For entry', () => {
    expect(clientIp(new Headers({ 'x-vercel-forwarded-for': '203.0.113.1', 'x-forwarded-for': '198.51.100.9' }))).toBe('203.0.113.1')
    expect(clientIp(new Headers({ 'x-real-ip': '203.0.113.2' }))).toBe('203.0.113.2')
    expect(clientIp(new Headers({ 'x-forwarded-for': '203.0.113.3, 10.0.0.1' }))).toBe('203.0.113.3')
    expect(clientIp(new Headers())).toBe('unknown')
  })
})

describe('createRateLimiter', () => {
  it('allows `limit` hits per key in a window, then says how long to wait', () => {
    const limiter = createRateLimiter({ limit: 2, windowMs: 60_000 })
    expect(limiter.hit('a', 0).allowed).toBe(true)
    expect(limiter.hit('a', 1_000).allowed).toBe(true)
    expect(limiter.hit('a', 2_000)).toEqual({ allowed: false, retryAfterSeconds: 58 })
    expect(limiter.hit('b', 2_000).allowed).toBe(true)
    // A new window starts once the old one is over.
    expect(limiter.hit('a', 60_000).allowed).toBe(true)
  })

  it('keeps at most maxKeys counters, dropping expired ones first and then the oldest', () => {
    const limiter = createRateLimiter({ limit: 1, windowMs: 1_000, maxKeys: 2 })
    limiter.hit('a', 0)
    limiter.hit('b', 500)
    // "a" has expired at 1200 and makes room: "b" keeps its count.
    limiter.hit('c', 1_200)
    expect(limiter.hit('b', 1_300).allowed).toBe(false)
    // Nothing has expired at 1400: the oldest ("b") goes, so it starts again.
    limiter.hit('d', 1_400)
    expect(limiter.hit('b', 1_450).allowed).toBe(true)
  })
})
