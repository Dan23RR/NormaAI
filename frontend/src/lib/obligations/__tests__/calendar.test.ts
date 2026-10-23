import { describe, it, expect } from 'vitest'
import { OBLIGATION_DATA, obligations, upcoming, past, groupByMonth, isPast } from '../calendar'
import { parseIsoDate, toIsoDate } from '../dates'
import { formatDate, formatMonthHeading } from '@/i18n/format'
import { textContextFor } from '@/test/i18n'

const TODAY = new Date(2026, 9, 23) // 23 ottobre 2026
const it_ = textContextFor('it')
const en = textContextFor('en')
const LIST = obligations(it_)

describe('obligations', () => {
  it('every entry is dated, sourced and verified on 2026-10-23', () => {
    expect(OBLIGATION_DATA.length).toBeGreaterThanOrEqual(12)
    for (const o of LIST) {
      expect(o.date).toMatch(/^\d{4}-\d{2}-\d{2}$/)
      expect(o.verifiedOn).toBe('2026-10-23')
      expect(o.source.act.length).toBeGreaterThan(0)
      expect(o.sourceNote.length).toBeGreaterThan(0)
      expect(o.title.length).toBeGreaterThan(0)
      expect(o.who.length).toBeGreaterThan(0)
    }
  })
  it('has unique ids', () => {
    const ids = OBLIGATION_DATA.map((o) => o.id)
    expect(new Set(ids).size).toBe(ids.length)
  })
  it('holds the dates the repository states', () => {
    const byId = Object.fromEntries(OBLIGATION_DATA.map((o) => [o.id, o.date]))
    expect(byId['aiact-art50']).toBe('2026-08-02')
    expect(byId['cra-reporting']).toBe('2026-09-11')
    expect(byId['cra-full-application']).toBe('2027-12-11')
    expect(byId['csddd-transposition']).toBe('2028-07-26')
    expect(byId['csddd-first-compliance']).toBe('2029-07-26')
    expect(byId['omnibus-in-force']).toBe('2026-03-18')
    expect(byId['aiact-high-risk-annex-iii']).toBe('2027-12-02')
  })
  it('speaks the language of the interface with the official act names', () => {
    const entry = obligations(en).find((o) => o.id === 'aiact-art50')
    expect(entry?.title).toBe('AI Act: transparency obligations of Art. 50')
    expect(entry?.source.act).toBe('Regulation (EU) 2024/1689 (AI Act)')
    expect(entry?.source.url).toContain('/legal-content/EN/')
    const italian = LIST.find((o) => o.id === 'aiact-art50')
    expect(italian?.source.act).toBe('Regolamento (UE) 2024/1689 (AI Act)')
  })
})

describe('upcoming', () => {
  it('returns only entries inside the window, ascending', () => {
    const list = upcoming(TODAY, 365, LIST)
    const ids = list.map((o) => o.id)
    expect(ids).toContain('aiact-legacy-marking')
    expect(ids).toContain('csrd-prepare-fy2027')
    expect(ids).toContain('csddd-guidelines')
    expect(ids).not.toContain('cra-reporting') // 11 settembre 2026, già passata
    expect(ids).not.toContain('csddd-transposition') // 26 luglio 2028, oltre i 12 mesi
    const dates = list.map((o) => o.date)
    expect([...dates].sort()).toEqual(dates)
  })
  it('is inclusive at both ends of the window', () => {
    expect(upcoming(new Date(2026, 11, 2), 0, LIST).map((o) => o.id)).toEqual(['aiact-legacy-marking'])
    expect(upcoming(new Date(2026, 11, 1), 1, LIST).map((o) => o.id)).toEqual(['aiact-legacy-marking'])
    expect(upcoming(new Date(2026, 11, 3), 10, LIST)).toHaveLength(0)
  })
  it('does not include the day before the window starts', () => {
    const list = upcoming(new Date(2026, 8, 12), 365, LIST)
    expect(list.map((o) => o.id)).not.toContain('cra-reporting')
  })
})

describe('past', () => {
  it('returns entries before today, most recent first', () => {
    const list = past(TODAY, LIST)
    expect(list[0].id).toBe('cra-reporting')
    expect(list.map((o) => o.id)).toContain('aiact-art50')
    expect(list.every((o) => isPast(o, TODAY))).toBe(true)
  })
})

describe('groupByMonth', () => {
  it('groups the next twelve months by month in order', () => {
    const groups = groupByMonth(upcoming(TODAY, 365, LIST))
    expect(groups.map((g) => g.key)).toEqual(['2026-12', '2027-01', '2027-04', '2027-07'])
    expect(groups[0].items.map((o) => o.id)).toEqual(['aiact-legacy-marking', 'csrd-prepare-fy2027'])
    expect(formatMonthHeading(groups[0].firstDay, 'it-IT')).toBe('Dicembre 2026')
    expect(formatMonthHeading(groups[0].firstDay, 'en-GB')).toBe('December 2026')
  })
})

describe('dates', () => {
  it('formats long dates and precisions per language', () => {
    expect(formatDate('2026-08-02', it_)).toBe('2 agosto 2026')
    expect(formatDate('2029-07-01', it_, 'month')).toBe('luglio 2029')
    expect(formatDate('2027-01-01', it_, 'quarter')).toBe('primo trimestre 2027')
    expect(formatDate('2028-04-01', it_, 'quarter')).toBe('secondo trimestre 2028')
    expect(formatDate('2026-08-02', en)).toBe('2 August 2026')
    expect(formatDate('2029-07-01', en, 'month')).toBe('July 2029')
    expect(formatDate('2027-01-01', en, 'quarter')).toBe('Q1 2027')
  })
  it('parses and serialises without a time-zone shift', () => {
    expect(toIsoDate(parseIsoDate('2026-12-02'))).toBe('2026-12-02')
  })
})
