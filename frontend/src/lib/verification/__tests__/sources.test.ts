import { createHash } from 'node:crypto'
import { describe, it, expect } from 'vitest'
import registry from '../sources.json'
import outcomes from '../sources.verified.json'
import { LAST_CHECK_ON, LEGAL_SOURCE_IDS, actName, legalSource, verificationOf, verifiedOn } from '../index'
import { CALENDAR_SOURCE_IDS, OBLIGATION_DATA } from '@/lib/obligations/calendar'
import { RULE_SOURCES, SCOPE_DATES, SCOPE_DATE_SOURCES } from '@/lib/scope/rules'

const RULE_IDS = Object.values(RULE_SOURCES) as string[]
const USED_IDS = Array.from(new Set([...RULE_IDS, ...CALENDAR_SOURCE_IDS]))
const RECORD_IDS = outcomes.sources.map((r) => r.id)

/** The fingerprint scripts/verify_site_sources.py stores for an entry: it changes when what is checked changes. */
function fingerprint(id: string): string {
  const s = legalSource(id)
  const parts = [s.kind, s.act, s.article, s.paragraph, s.lang, s.excerpt, String(s.annex ?? ''), s.url ?? '', s.in_force_from ?? '']
  return `sha256:${createHash('sha256').update(parts.join('\x1f'), 'utf8').digest('hex')}`
}

const MONTHS = [
  'gennaio',
  'febbraio',
  'marzo',
  'aprile',
  'maggio',
  'giugno',
  'luglio',
  'agosto',
  'settembre',
  'ottobre',
  'novembre',
  'dicembre',
]

/**
 * True when what the script read for a source carries the date: the full date
 * in the official wording, the month and year where the ordinal of the first
 * day was left out of the excerpt, a day and month that recur "every year",
 * or the date Normattiva gives as the start of the article's validity.
 */
function carriesDate(id: string, iso: string): boolean {
  const record = verificationOf(id)
  if (!record) return false
  const [year, month, day] = iso.split('-').map(Number)
  const quote = (record.official_quote ?? '').replace(/\s+/g, ' ')
  const name = MONTHS[month - 1]
  if (new RegExp(`(^|\\D)${day}[°º]? ${name} ${year}`).test(quote)) return true
  if (day === 1 && quote.includes(`[...] ${name} ${year}`)) return true
  if (new RegExp(`(^|\\D)${day}[°º]? ${name}`).test(quote) && quote.includes('ogni anno')) return true
  return record.in_force_from === iso
}

describe('registry of legal sources', () => {
  it('names every act in both languages and labels every provision', () => {
    expect(LEGAL_SOURCE_IDS.length).toBeGreaterThan(100)
    expect(new Set(LEGAL_SOURCE_IDS).size).toBe(LEGAL_SOURCE_IDS.length)
    for (const id of LEGAL_SOURCE_IDS) {
      const s = legalSource(id)
      expect(['eurlex', 'normattiva', 'document'], id).toContain(s.kind)
      expect(s.excerpt.length, id).toBeGreaterThanOrEqual(20)
      expect(s.label.it.trim(), id).not.toBe('')
      expect(s.label.en.trim(), id).not.toBe('')
      expect(actName(s.act, 'it'), id).not.toBe(s.act)
      expect(actName(s.act, 'en'), id).not.toBe(s.act)
      if (s.kind === 'eurlex') expect(s.act, id).toMatch(/^3\d{4}[A-Z]\d{4}$/)
      if (s.kind === 'normattiva') expect(s.act, id).toMatch(/^urn:nir:stato:[a-z.]+:\d{4}-\d{2}-\d{2};\d+$/)
      if (s.kind === 'document') expect(s.url, id).toMatch(/^https:\/\/www\.acn\.gov\.it\//)
    }
    expect(Object.keys(registry.acts).sort()).toEqual(Array.from(new Set(LEGAL_SOURCE_IDS.map((id) => legalSource(id).act))).sort())
  })

  it('holds only provisions a rule or a calendar entry uses', () => {
    expect(LEGAL_SOURCE_IDS.filter((id) => !USED_IDS.includes(id))).toEqual([])
  })

  it('throws on an id that is not in the registry', () => {
    expect(() => legalSource('non-esiste')).toThrow(/Unknown legal source/)
    expect(verificationOf('non-esiste')).toBeUndefined()
    expect(verifiedOn('non-esiste')).toBeUndefined()
  })
})

describe('outcomes of scripts/verify_site_sources.py', () => {
  it('cover every source id a rule uses', () => {
    expect(RULE_IDS.filter((id) => !LEGAL_SOURCE_IDS.includes(id))).toEqual([])
    expect(RULE_IDS.filter((id) => !RECORD_IDS.includes(id))).toEqual([])
  })

  it('cover every source id a calendar entry uses', () => {
    expect(CALENDAR_SOURCE_IDS.filter((id) => !LEGAL_SOURCE_IDS.includes(id))).toEqual([])
    expect(CALENDAR_SOURCE_IDS.filter((id) => !RECORD_IDS.includes(id))).toEqual([])
  })

  it('hold no record for an id that left the registry', () => {
    expect(RECORD_IDS.filter((id) => !LEGAL_SOURCE_IDS.includes(id))).toEqual([])
    expect(new Set(RECORD_IDS).size).toBe(RECORD_IDS.length)
  })

  it('were produced for the registry as it is now: no entry was edited after the check', () => {
    for (const id of LEGAL_SOURCE_IDS) {
      expect(verificationOf(id)?.fingerprint, id).toBe(fingerprint(id))
    }
  })

  it('verify every source the rules and the calendar cite, each with its date and the official wording', () => {
    expect(LAST_CHECK_ON).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    for (const id of USED_IDS) {
      const record = verificationOf(id)
      expect(record?.status, id).toBe('verified')
      expect(record?.verified_on, id).toMatch(/^\d{4}-\d{2}-\d{2}$/)
      expect(verifiedOn(id), id).toBe(record?.verified_on)
      expect((record?.official_quote ?? '').length, id).toBeGreaterThanOrEqual(20)
      expect(record?.version, id).toBeTruthy()
      expect(record?.url, id).toMatch(/^https:\/\/(eur-lex\.europa\.eu|www\.normattiva\.it|www\.acn\.gov\.it)\//)
    }
  })

  it('read EU acts in a consolidated or original CELLAR text and Italian acts in the text in force', () => {
    for (const id of LEGAL_SOURCE_IDS) {
      const { kind } = legalSource(id)
      const record = verificationOf(id)
      if (kind === 'eurlex') expect(record?.version, id).toMatch(/^[03]\d{4}[A-Z]\d{4}(-\d{8})?$/)
      if (kind === 'normattiva') expect(record?.version, id).toMatch(/^vigente al \d{4}-\d{2}-\d{2}$/)
      if (kind === 'document') expect(record?.version, id).toMatch(/^sha256:[0-9a-f]{64}$/)
    }
  })
})

describe('dates stated by the rules and the calendar', () => {
  it('every date of the scope rules is in the text of its source', () => {
    for (const key of Object.keys(SCOPE_DATES) as Array<keyof typeof SCOPE_DATES>) {
      const id = RULE_SOURCES[SCOPE_DATE_SOURCES[key]]
      expect(carriesDate(id, SCOPE_DATES[key]), `${key} ${SCOPE_DATES[key]} in ${id}`).toBe(true)
    }
  })

  it('every calendar date is in the text of its own source', () => {
    for (const o of OBLIGATION_DATA) {
      expect(carriesDate(o.source, o.date), `${o.id} ${o.date} in ${o.source}`).toBe(true)
    }
  })

  it('a date that is not in the text is caught', () => {
    expect(carriesDate('mach-54', '2027-01-14')).toBe(false)
    expect(carriesDate('dlgs-138-2024-7-1', '2027-03-28')).toBe(false)
    expect(carriesDate('dlgs-179-2026-41-1', '2026-10-09')).toBe(false)
  })
})
