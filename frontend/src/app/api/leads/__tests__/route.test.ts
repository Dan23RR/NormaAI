// @vitest-environment node
// (a browser-like environment drops the Cookie header of a Request it builds)
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { NextRequest } from 'next/server'

type Post = (req: NextRequest) => Promise<Response>
let POST: Post

function leadRequest(body: unknown, { cookie, ip }: { cookie?: string; ip?: string } = {}): NextRequest {
  return new NextRequest('https://normaai.org/api/leads', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(cookie ? { cookie } : {}),
      ...(ip ? { 'x-forwarded-for': ip } : {}),
    },
    body: typeof body === 'string' ? body : JSON.stringify(body),
  })
}

/** The emails the route asked Resend to send. */
function sentEmails(fetchMock: ReturnType<typeof vi.fn>): Array<{ to: string[]; subject: string; text: string; reply_to?: string }> {
  return fetchMock.mock.calls.map(([, init]) => JSON.parse((init as RequestInit).body as string))
}

/** The structured lines the route wrote to the function log. */
function logged(event: string): Array<Record<string, unknown>> {
  return (console.log as unknown as ReturnType<typeof vi.fn>).mock.calls
    .map(([line]) => JSON.parse(String(line)) as Record<string, unknown>)
    .filter((entry) => entry.event === event)
}

describe('POST /api/leads', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(async () => {
    // A fresh module, so the per-address counters start at zero in every test.
    vi.resetModules()
    ;({ POST } = (await import('../route')) as unknown as { POST: Post })
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
    const res = await POST(leadRequest({ email: 'ada@example.test' }, { cookie: 'normaai.locale=en' }))
    expect((await res.json()).message).toBe('Request recorded. Download the Codex with the button below.')
  })

  it('never writes to the address in the form: one email, to the operator, with it as reply-to', async () => {
    vi.stubEnv('RESEND_API_KEY', 'test-key')
    const res = await POST(leadRequest({ email: 'victim@example.test', source: 'codex_download' }))
    expect(res.status).toBe(200)
    const emails = sentEmails(fetchMock)
    expect(emails).toHaveLength(1)
    expect(emails[0].to).toEqual(['info@normaai.org'])
    expect(emails[0].reply_to).toBe('victim@example.test')
  })

  it('sends the notification to the inbox configured for it', async () => {
    vi.stubEnv('RESEND_API_KEY', 'test-key')
    vi.stubEnv('LEADS_NOTIFY_EMAIL', 'operator@example.test')
    await POST(leadRequest({ email: 'ada@example.test' }))
    expect(sentEmails(fetchMock).map((email) => email.to)).toEqual([['operator@example.test']])
  })

  it('passes on the situations ticked in the AI Act checker, so a reply can name their passages', async () => {
    vi.stubEnv('RESEND_API_KEY', 'test-key')
    await POST(leadRequest({ email: 'ada@example.test', role: 'aiact_checker', source: 'aiact_checker:in:chat+gen', lead_ref: 'scope-aiact' }))
    const [notification] = sentEmails(fetchMock)
    expect(notification.subject).toBe('[NormaAI lead - scope-aiact] ada@example.test')
    expect(notification.text).toContain('Source:  aiact_checker:in:chat+gen')
    expect(notification.text).toContain('Ruolo:   aiact_checker')
  })

  it('rejects an invalid address and sends nothing', async () => {
    vi.stubEnv('RESEND_API_KEY', 'test-key')
    for (const email of ['not-an-address', 'a b@example.test', '"x"@example.test', 'x@example', `${'a'.repeat(250)}@example.test`, 42]) {
      const res = await POST(leadRequest({ email }))
      expect(res.status, String(email)).toBe(422)
    }
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('rejects a body that is not one of the forms', async () => {
    vi.stubEnv('RESEND_API_KEY', 'test-key')
    const cases: unknown[] = ['not json', '[]', '"ada@example.test"', 'null', { email: 'ada@example.test', source: 'newsletter' }]
    for (const body of cases) {
      const res = await POST(leadRequest(body))
      expect(res.status, JSON.stringify(body)).toBe(422)
    }
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('refuses a body larger than a lead', async () => {
    const res = await POST(leadRequest({ email: 'ada@example.test', org_name: 'x'.repeat(5000) }))
    expect(res.status).toBe(413)
  })

  it('keeps the subject on one line and drops what the forms never send', async () => {
    vi.stubEnv('RESEND_API_KEY', 'test-key')
    await POST(
      leadRequest({ email: 'ada@example.test', org_name: 'Rossi\r\nBcc: x@example.test', role: 'CEO <script>', lead_ref: 'a b' }),
    )
    const [notification] = sentEmails(fetchMock)
    expect(notification.subject).toBe('[NormaAI lead] ada@example.test - Rossi Bcc: x@example.test')
    expect(notification.text).toContain('Ruolo:   -')
    expect(notification.text).toContain('LeadRef: - (traffico organico)')
  })

  it('pretends success to a filled honeypot and sends nothing', async () => {
    vi.stubEnv('RESEND_API_KEY', 'test-key')
    const res = await POST(leadRequest({ email: 'bot@example.test', contact_time: 'now' }))
    const data = await res.json()
    expect(res.status).toBe(200)
    expect(data.download_url).toBeUndefined()
    expect(fetchMock).not.toHaveBeenCalled()
    expect(logged('lead_honeypot')).toHaveLength(1)
  })

  it('also reads the honeypot key of pages cached before the rename', async () => {
    vi.stubEnv('RESEND_API_KEY', 'test-key')
    const res = await POST(leadRequest({ email: 'bot@example.test', website: 'https://spam.example' }))
    expect((await res.json()).download_url).toBeUndefined()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('takes 10 requests an hour from one address, then answers 429 with Retry-After', async () => {
    vi.stubEnv('RESEND_API_KEY', '')
    for (let i = 0; i < 10; i++) {
      expect((await POST(leadRequest({ email: 'ada@example.test' }, { ip: '203.0.113.7' }))).status).toBe(200)
    }
    const refused = await POST(leadRequest({ email: 'ada@example.test' }, { ip: '203.0.113.7' }))
    expect(refused.status).toBe(429)
    expect(Number(refused.headers.get('Retry-After'))).toBeGreaterThan(3000)
    expect((await refused.json()).detail).toBe('Troppe richieste recenti dallo stesso indirizzo. Riprova tra un’ora.')
    // Another address is counted on its own.
    expect((await POST(leadRequest({ email: 'bea@example.test' }, { ip: '198.51.100.4' }))).status).toBe(200)
  })

  it('counts the requests a bot fills in, so the honeypot is no way around the limit', async () => {
    for (let i = 0; i < 10; i++) {
      await POST(leadRequest({ email: 'bot@example.test', contact_time: 'x' }, { ip: '203.0.113.9' }))
    }
    expect((await POST(leadRequest({ email: 'ada@example.test' }, { ip: '203.0.113.9' }))).status).toBe(429)
  })
})
