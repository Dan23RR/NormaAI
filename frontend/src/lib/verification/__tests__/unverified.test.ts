/**
 * What the interface does when the check did NOT verify a source: the
 * outcomes file is replaced here with one where a calendar source failed,
 * a rule source was unreachable and another has no record at all.
 */
import { describe, it, expect, vi } from 'vitest'
import { textContextFor } from '@/test/i18n'

vi.mock('../sources.verified.json', async (importOriginal) => {
  const original = (await importOriginal()) as {
    default: { generated_on: string; tool: string; sources: Array<Record<string, unknown>> }
  }
  const sources = original.default.sources
    .filter((r) => r.id !== 'mach-17')
    .map((r) => {
      if (r.id === 'mach-54') return { ...r, status: 'failed', verified_on: null, official_quote: null }
      if (r.id === 'ai-act-50-1') return { ...r, status: 'unreachable', verified_on: null, official_quote: null }
      return r
    })
  return { default: { ...original.default, sources } }
})

const it_ = textContextFor('it')
const en = textContextFor('en')

describe('a source the check did not verify', () => {
  it('is shown as indicated, not yet verified, with no date and no quote', async () => {
    const { scopeSource, verificationLabel } = await import('@/lib/scope/sources')
    for (const id of ['mach-54', 'ai-act-50-1', 'mach-17']) {
      const source = scopeSource(id, it_)
      expect(source.status, id).toBe('unverified')
      expect(source.verifiedAt, id).toBeUndefined()
      expect(source.quote, id).toBeUndefined()
      expect(source.act.length, id).toBeGreaterThan(0)
      expect(source.url, id).toMatch(/^https:\/\//)
      expect(verificationLabel(source, it_), id).toBe('Fonte indicata, non ancora verificata')
      expect(verificationLabel(scopeSource(id, en), en), id).toBe('Source indicated, not yet verified')
    }
  })

  it('keeps its neighbours verified, each with its own date', async () => {
    const { scopeSource, verificationLabel } = await import('@/lib/scope/sources')
    const { verifiedOn } = await import('@/lib/verification')
    const source = scopeSource('mach-10-1', it_)
    expect(source.status).toBe('verified')
    expect(source.verifiedAt).toBe(verifiedOn('mach-10-1'))
    expect(verificationLabel(source, it_)).toMatch(/^Verificata (il |l')\d{1,2} \p{L}+ \d{4} sul testo consolidato al /u)
  })

  it('takes its calendar entry out of the calendar', async () => {
    const { obligations, verifiedOnly } = await import('@/lib/obligations/calendar')
    const all = obligations(it_)
    const shown = verifiedOnly(all)
    expect(all.find((o) => o.id === 'machinery-application')?.verifiedOn).toBeUndefined()
    expect(shown.map((o) => o.id)).not.toContain('machinery-application')
    expect(shown.length).toBe(all.length - 1)
  })

  it('still lets the rule answer, with the source marked as not verified', async () => {
    const { assessScope } = await import('@/lib/scope/rules')
    const { EMPTY_INPUT, keysToMachinery } = await import('@/lib/scope/query')
    const result = assessScope({ ...EMPTY_INPUT, machinery: keysToMachinery(['imp']) }, it_).results.find(
      (r) => r.framework === 'MACHINERY',
    )
    expect(result?.status).toBe('in_scope')
    const byId = Object.fromEntries((result?.sources ?? []).map((s) => [s.id, s.status]))
    expect(byId['mach-54']).toBe('unverified')
    expect(byId['mach-17']).toBe('unverified')
    expect(byId['mach-13-1']).toBe('verified')
  })
})
