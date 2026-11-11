// @vitest-environment node
// (a browser-like environment drops the Cookie header of a Request it builds)
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { NextRequest } from 'next/server'
import { POST } from '../route'

function leadRequest(body: unknown, cookie?: string): NextRequest {
  return new NextRequest('https://normaai.org/api/leads', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(cookie ? { cookie } : {}) },
    body: JSON.stringify(body),
  })
}

/** The plain-text bodies of the emails the route asked Resend to send. */
function sentEmails(fetchMock: ReturnType<typeof vi.fn>): Array<{ to: string[]; subject: string; text: string }> {
  return fetchMock.mock.calls.map(([, init]) => JSON.parse((init as RequestInit).body as string))
}

describe('POST /api/leads', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn(async () => new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    vi.spyOn(console, 'log').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
    vi.restoreAllMocks()
  })

  it('answers with the link and says only what happened, promising no delivery time', async () => {
    vi.stubEnv('RESEND_API_KEY', '')
    const res = await POST(leadRequest({ email: 'ada@example.test', source: 'codex_download' }))
    const data = await res.json()
    expect(res.status).toBe(200)
    expect(data.download_url).toBe('/codex-post-omnibus-2025-2029.pdf')
    expect(data.message).toBe('Richiesta registrata. Scarica il Codex con il pulsante qui sotto.')
    expect(data.message).not.toMatch(/24 ore|subito|entro/)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('answers in English when the interface cookie says so', async () => {
    vi.stubEnv('RESEND_API_KEY', '')
    const res = await POST(leadRequest({ email: 'ada@example.test' }, 'normaai.locale=en'))
    expect((await res.json()).message).toBe('Request recorded. Download the Codex with the button below.')
  })

  it('rejects an invalid address and sends nothing', async () => {
    vi.stubEnv('RESEND_API_KEY', 'test-key')
    const res = await POST(leadRequest({ email: 'not-an-address' }))
    expect(res.status).toBe(422)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('pretends success to a filled honeypot and sends nothing', async () => {
    vi.stubEnv('RESEND_API_KEY', 'test-key')
    const res = await POST(leadRequest({ email: 'bot@example.test', contact_time: 'now' }))
    const data = await res.json()
    expect(res.status).toBe(200)
    expect(data.download_url).toBeUndefined()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('writes to an AI Act lead about the law in force: applicable since 2 August, next date 2 December 2026', async () => {
    vi.stubEnv('RESEND_API_KEY', 'test-key')
    await POST(leadRequest({ email: 'ada@example.test', source: 'aiact_checker:in:chat+gen', lead_ref: 'scope-aiact' }))
    const [notification, delivery] = sentEmails(fetchMock)
    expect(notification.text).toContain('Source:  aiact_checker:in:chat+gen')
    expect(delivery.to).toEqual(['ada@example.test'])
    expect(delivery.text).toContain('si applica dal 2 agosto 2026')
    expect(delivery.text).toContain('entro il 2 dicembre 2026')
    expect(delivery.text).toContain('30 minuti')
    expect(delivery.text).not.toMatch(/prima del 2 agosto|20 minuti|17 pagine/)
    expect(delivery.text).toContain('https://normaai.org/codex-post-omnibus-2025-2029.pdf')
  })

  it('writes to a Codex lead with the thresholds of the directive and the same call length', async () => {
    vi.stubEnv('RESEND_API_KEY', 'test-key')
    await POST(leadRequest({ email: 'ada@example.test', source: 'scope_checker:filo', lead_ref: 'scope-csrd' }))
    const [, delivery] = sentEmails(fetchMock)
    expect(delivery.text).toContain('più di 1.000')
    expect(delivery.text).toContain('più di 450 milioni di euro')
    expect(delivery.text).toContain('applicazione dal 26 luglio 2029')
    expect(delivery.text).toContain('30 minuti')
    expect(delivery.text).not.toMatch(/20 minuti|17 pagine|·|—|–/)
  })
})
