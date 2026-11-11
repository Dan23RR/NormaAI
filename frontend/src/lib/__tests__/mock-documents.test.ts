import { describe, it, expect, vi, beforeEach } from 'vitest'
import { GROUPS, type DocumentCheck, type Finding } from '@/components/controlla/types'
import { asCheck, asList } from '@/components/controlla/documents-api'

// The api client in demo mode, without the waits that imitate the server.
vi.mock('@/lib/auth', () => ({
  isDemoMode: () => true,
  getAccessToken: () => 'demo.jwt.token',
  getRefreshToken: () => null,
  setTokens: vi.fn(),
  clearTokens: vi.fn(),
  isTokenExpired: () => false,
}))

vi.mock('@/lib/mock-data', async (original) => ({
  ...(await original<typeof import('@/lib/mock-data')>()),
  mockDelay: () => Promise.resolve(),
}))

import { api } from '../api'
import { ApiError } from '../api-error'
import { DEMO_CLIENTS } from '../mock-data'
import { DEMO_DOCUMENTS, DEMO_UPLOAD_RESULT_ID, demoDocumentsRoute, demoReportHtml, resetDemoDocuments } from '../mock-documents'

const byId = (id: string): DocumentCheck => {
  const doc = DEMO_DOCUMENTS.find((d) => d.id === id)
  if (!doc) throw new Error(`no demo document ${id}`)
  return doc
}
const withStatus = (doc: DocumentCheck, code: string): Finding => {
  const finding = doc.findings.find((f) => f.status.code === code)
  if (!finding) throw new Error(`no finding ${code} in ${doc.id}`)
  return finding
}

describe('DEMO_DOCUMENTS', () => {
  it('has at least three checks with unique ids, each tied to an existing demo client or to none', () => {
    expect(DEMO_DOCUMENTS.length).toBeGreaterThanOrEqual(3)
    expect(new Set(DEMO_DOCUMENTS.map((d) => d.id)).size).toBe(DEMO_DOCUMENTS.length)
    const clientIds = new Set(DEMO_CLIENTS.map((c) => c.id))
    for (const doc of DEMO_DOCUMENTS) {
      if (doc.client_id !== null) expect(clientIds.has(doc.client_id), doc.id).toBe(true)
      expect(doc.document_sha256).toMatch(/^[0-9a-f]{64}$/)
      expect(new Date(doc.checked_at).getTime(), doc.id).not.toBeNaN()
    }
  })

  it('keeps counts, status and dependencies consistent with the findings', () => {
    for (const doc of DEMO_DOCUMENTS) {
      for (const group of GROUPS) {
        expect(doc.counts[group], `${doc.id} ${group}`).toBe(doc.findings.filter((f) => f.group === group).length)
      }
      const worst = GROUPS.find((group) => group !== 'non_coperto' && doc.counts[group] > 0) ?? 'a_posto'
      expect(doc.status, doc.id).toBe(worst)
      // Every provision found in an EU act is recorded as a dependency.
      for (const finding of doc.findings) {
        if (finding.act?.source !== 'eurlex' || !finding.provision) continue
        expect(
          doc.dependencies.some((d) => d.act === finding.act?.id && d.key === finding.provision?.key),
          `${doc.id} ${finding.id}`,
        ).toBe(true)
      }
      expect(doc.needs_review, doc.id).toBe(doc.dependencies.some((d) => d.state === 'changed' || d.state === 'removed'))
    }
  })

  it('stores what the API stores: a reference, at most 160 characters of context, a link to an official source', () => {
    for (const doc of DEMO_DOCUMENTS) {
      for (const finding of doc.findings) {
        const where = `${doc.id} ${finding.id}`
        expect(finding.context.length, where).toBeLessThanOrEqual(160)
        expect(finding.context, where).toContain(finding.raw)
        expect(finding.messages.length, where).toBeGreaterThan(0)
        expect(finding.url, where).toMatch(/^https:\/\/(eur-lex\.europa\.eu|www\.normattiva\.it)\//)
      }
    }
  })

  it('survives the reading the page does of a server answer', () => {
    for (const doc of DEMO_DOCUMENTS) expect(asCheck(JSON.parse(JSON.stringify(doc)))).toEqual(doc)
  })

  it('has an altered quote: article 33(1) GDPR with 48 hours where the regulation says 72', () => {
    const finding = withStatus(byId('demo-doc-gdpr'), 'alterata')
    expect(finding.group).toBe('correggere')
    expect(finding.act?.id).toBe('32016R0679')
    expect(finding.provision).toEqual({ key: 'art:33', label: 'art. 33, par. 1', paragraphs: ['1'] })
    expect(finding.altered_quote).toBe(finding.quotes[0])
    expect(finding.quotes[0]).toContain('entro 48 ore')
    expect(finding.official_quote).toBe(
      'senza ingiustificato ritardo e, ove possibile, entro 72 ore dal momento in cui ne è venuto a conoscenza',
    )
    expect(finding.differences).toEqual([{ quoted: '48', official: '72' }])
  })

  it('has a superseded quote of article 4 of the AI Act with the article then and now', () => {
    const finding = withStatus(byId('demo-doc-ai'), 'superata')
    expect(finding.group).toBe('correggere')
    expect(finding.act?.id).toBe('32024R1689')
    expect(finding.provision?.key).toBe('art:4')
    expect(finding.version).toEqual({ id: '02024R1689-20260727', as_of: '2026-07-27', label: 'testo consolidato al 27/07/2026' })
    expect(finding.before?.version_label).toBe('testo originale')
    // The words the amendment replaced, and the ones it put in their place.
    expect(finding.before?.text).toContain('adottano misure per garantire nella misura del possibile un livello sufficiente di alfabetizzazione')
    expect(finding.after_text).toContain("adottano misure volte a sostenere lo sviluppo dell'alfabetizzazione")
    expect(finding.after_text).toContain('Tale obbligo non impone ai fornitori o ai deployer di garantire un livello specifico')
    // The quote of the document is in the old text, word for word, and not in the new one.
    expect(finding.before?.text).toContain(finding.quotes[0])
    expect(finding.after_text).not.toContain(finding.quotes[0])
  })

  it('has a check that surveillance marked for review, with the provisions that changed', () => {
    const doc = byId('demo-doc-csddd')
    expect(doc.needs_review).toBe(true)
    expect(doc.watch).toBe(true)
    const changed = doc.dependencies.filter((d) => d.state === 'changed')
    expect(changed.map((d) => d.article)).toEqual(['Art. 2', 'Art. 10', 'Art. 37'])
    for (const dependency of changed) {
      // Checked on the text of the day, found changed in the newer one.
      expect(dependency.version).toBe('02024L1760-20250417')
      expect(dependency.current_version).toBe('02024L1760-20260318')
      expect(dependency.changed_at! > doc.checked_at).toBe(true)
    }
    expect(doc.dependencies.find((d) => d.article === 'Art. 14')?.state).toBe('current')
    // Nothing was wrong on the day of the check; after the re-check the references
    // to the changed articles are to correct, with the article then and now.
    expect(doc.status).toBe('correggere')
    const moved = doc.findings.filter((f) => f.group === 'correggere')
    expect(moved.map((f) => f.provision?.key)).toEqual(['art:2', 'art:10', 'art:37'])
    for (const finding of moved) {
      expect(finding.status).toEqual({ code: 'cambiato_dopo_controllo', label: 'Cambiato dopo il controllo' })
      expect(finding.version?.id).toBe('02024L1760-20260318')
      expect(finding.before?.version_id).toBe('02024L1760-20250417')
      expect(finding.after_text).toBeTruthy()
    }
    expect(doc.findings.find((f) => f.provision?.key === 'art:14')?.group).toBe('a_posto')
  })

  it('has a check without surveillance and without a client, on an English document', () => {
    const doc = byId('demo-doc-clause')
    expect(doc.watch).toBe(false)
    expect(doc.client_id).toBeNull()
    expect(doc.lang).toBe('EN')
    expect(withStatus(doc, 'verificata').url).toContain('/legal-content/EN/TXT/')
  })
})

describe('demo interception of the documents API', () => {
  beforeEach(() => {
    resetDemoDocuments()
  })

  it('lists the checks newest first, without findings', async () => {
    const res = asList(await api.get('/api/v1/documents/checks?limit=20&offset=0'))
    expect(res.total).toBe(DEMO_DOCUMENTS.length)
    expect(res.items.map((i) => i.id)).toEqual(['demo-doc-gdpr', 'demo-doc-ai', 'demo-doc-clause', 'demo-doc-csddd'])
    const raw = await api.get<{ items: Array<Record<string, unknown>> }>('/api/v1/documents/checks')
    expect(raw.items[0]).not.toHaveProperty('findings')
    expect(raw.items[0]).not.toHaveProperty('dependencies')
  })

  it('filters by review, by client, and pages', async () => {
    const review = asList(await api.get('/api/v1/documents/checks?needs_review=true'))
    expect(review.items.map((i) => i.id)).toEqual(['demo-doc-csddd'])
    expect(review.total).toBe(1)

    const ofClient = asList(await api.get('/api/v1/documents/checks?client_id=demo-c5'))
    expect(ofClient.items.map((i) => i.id)).toEqual(['demo-doc-ai'])

    const nobody = asList(await api.get('/api/v1/documents/checks?client_id=missing'))
    expect(nobody).toEqual({ items: [], total: 0 })

    const second = asList(await api.get('/api/v1/documents/checks?limit=2&offset=2'))
    expect(second.items.map((i) => i.id)).toEqual(['demo-doc-clause', 'demo-doc-csddd'])
    expect(second.total).toBe(DEMO_DOCUMENTS.length)
  })

  it('returns one check in full, and the 404 of the server for one that is not there', async () => {
    const doc = asCheck(await api.get('/api/v1/documents/checks/demo-doc-ai'))
    expect(doc.findings).toHaveLength(4)
    expect(doc.dependencies).toHaveLength(4)

    const failure = await api.get('/api/v1/documents/checks/nope').catch((e: unknown) => e)
    expect(failure).toBeInstanceOf(ApiError)
    expect((failure as ApiError).code).toBe('requestFailed')
    expect((failure as ApiError).values).toEqual({ status: '404' })
  })

  it('answers an upload and a pasted text with the example check, never reading the file', async () => {
    const form = new FormData()
    form.append('file', new File(['riservato'], 'contratto riservato.docx'))
    const fromFile = asCheck(await api.upload('/api/v1/documents/check', form))
    expect(fromFile.id).toBe(DEMO_UPLOAD_RESULT_ID)
    // The example keeps its own name: the demo never presents it as the person's file.
    expect(fromFile.filename).toBe('Procedura violazioni dati personali.docx')

    const fromText = asCheck(await api.post('/api/v1/documents/check', { text: 'art. 13 del GDPR', filename: 'nota', watch: true }))
    expect(fromText.id).toBe(DEMO_UPLOAD_RESULT_ID)
  })

  it('still refuses the old upload route in the demo', async () => {
    const failure = await api.upload('/api/v1/documents/upload', new FormData()).catch((e: unknown) => e)
    expect(failure).toBeInstanceOf(ApiError)
    expect((failure as ApiError).code).toBe('uploadDemo')
  })

  it('re-checks without changing the example', async () => {
    const before = asCheck(await api.get('/api/v1/documents/checks/demo-doc-csddd'))
    const after = asCheck(await api.post('/api/v1/documents/checks/demo-doc-csddd/recheck', {}))
    expect(after).toEqual(before)
  })

  it('deletes a check until the page is reloaded, and brings the example back when it is asked for again', async () => {
    await api.del('/api/v1/documents/checks/demo-doc-gdpr')
    const left = asList(await api.get('/api/v1/documents/checks'))
    expect(left.items.map((i) => i.id)).not.toContain('demo-doc-gdpr')
    expect(left.total).toBe(DEMO_DOCUMENTS.length - 1)
    await expect(api.get('/api/v1/documents/checks/demo-doc-gdpr')).rejects.toBeInstanceOf(ApiError)
    await expect(api.del('/api/v1/documents/checks/demo-doc-gdpr')).rejects.toBeInstanceOf(ApiError)

    await api.post('/api/v1/documents/check', { text: 'x', filename: 'y' })
    expect(asList(await api.get('/api/v1/documents/checks')).total).toBe(DEMO_DOCUMENTS.length)
  })

  it('keeps the email preference in memory, never in the browser storage', async () => {
    const storage = { setItem: vi.fn(), getItem: vi.fn(() => null), removeItem: vi.fn(), clear: vi.fn() }
    vi.stubGlobal('sessionStorage', storage)
    vi.stubGlobal('localStorage', storage)
    expect(await api.get('/api/v1/documents/preferences')).toEqual({ email_digest: true })
    expect(await api.patch('/api/v1/documents/preferences', { email_digest: false })).toEqual({ email_digest: false })
    expect(await api.get('/api/v1/documents/preferences')).toEqual({ email_digest: false })
    await api.del('/api/v1/documents/checks/demo-doc-ai')
    expect(storage.setItem).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
  })

  it('serves the report of a check as an HTML page that says it is an example', async () => {
    const response = await api.fetchBlob('/api/v1/documents/checks/demo-doc-ai/report')
    expect(response.headers.get('Content-Type')).toContain('text/html')
    const html = await response.text()
    expect(html.startsWith('<!doctype html>')).toBe(true)
    expect(html).toContain('Demo con dati di esempio')
    expect(html).toContain('Policy uso IA.pdf')
    expect(html).toContain('<del>')
    expect(html).toContain('<ins>')
    // Nothing that could run in the page that shows it.
    expect(html).not.toMatch(/<script|onerror=|javascript:/i)
    await expect(api.fetchBlob('/api/v1/documents/checks/nope/report')).rejects.toBeInstanceOf(ApiError)
    // Reports of the other surfaces stay unavailable in the demo.
    const other = await api.fetchBlob('/api/v1/reports/gap-analysis', { method: 'POST' }).catch((e: unknown) => e)
    expect((other as ApiError).code).toBe('reportDemo')
  })

  it('leaves every other path alone', () => {
    expect(demoDocumentsRoute('GET', '/api/v1/clients')).toEqual({ handled: false })
    expect(demoDocumentsRoute('POST', '/api/v1/documents/upload')).toEqual({ handled: false })
    expect(demoDocumentsRoute('GET', '/api/v1/documents/check')).toEqual({ handled: false })
  })
})

describe('demoReportHtml', () => {
  it('escapes what comes from a document', () => {
    const doc = byId('demo-doc-gdpr')
    const hostile: DocumentCheck = {
      ...doc,
      filename: '<img src=x onerror=alert(1)>.docx',
      findings: [{ ...doc.findings[0], context: 'art. 33 <script>alert(1)</script>', quotes: ['"><b>x</b>'] }],
    }
    const html = demoReportHtml(hostile)
    expect(html).not.toContain('<script>')
    expect(html).not.toContain('<img')
    expect(html).not.toContain('<b>x</b>')
    expect(html).toContain('&lt;script&gt;')
  })
})
