import { describe, it, expect } from 'vitest'
import { CALENDAR_SOURCE_IDS, OBLIGATION_DATA, obligations, upcoming, past, groupByMonth, isPast, verifiedOnly } from '../calendar'
import { parseIsoDate, toIsoDate } from '../dates'
import { formatDate, formatMonthHeading } from '@/i18n/format'
import { hasLegalSource, verifiedOn } from '@/lib/verification'
import { textContextFor } from '@/test/i18n'

const TODAY = new Date(2026, 10, 11) // 11 novembre 2026
const it_ = textContextFor('it')
const en = textContextFor('en')
const LIST = obligations(it_)

describe('obligations', () => {
  it('every entry is dated to the day and written out in both languages', () => {
    expect(OBLIGATION_DATA.length).toBeGreaterThanOrEqual(20)
    for (const o of LIST) {
      expect(o.date).toMatch(/^\d{4}-\d{2}-\d{2}$/)
      expect(o.precision).toBe('day')
      expect(o.title.length).toBeGreaterThan(0)
      expect(o.who.length).toBeGreaterThan(0)
      expect(o.what.length).toBeGreaterThan(0)
    }
    for (const o of obligations(en)) {
      expect(o.title.length).toBeGreaterThan(0)
      expect(o.who.length).toBeGreaterThan(0)
      expect(o.what.length).toBeGreaterThan(0)
    }
  })

  it('has unique ids', () => {
    const ids = OBLIGATION_DATA.map((o) => o.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('gives every entry its own registry source and the date that source was verified on', () => {
    for (const data of OBLIGATION_DATA) {
      expect(hasLegalSource(data.source), data.id).toBe(true)
      for (const id of data.related) expect(hasLegalSource(id), `${data.id} ${id}`).toBe(true)
    }
    for (const o of LIST) {
      expect(o.source.status, o.id).toBe('verified')
      expect(o.verifiedOn, o.id).toBe(verifiedOn(o.source.id))
      expect(o.verifiedOn, o.id).toMatch(/^\d{4}-\d{2}-\d{2}$/)
      expect(o.source.quote, o.id).toBeTruthy()
      expect(o.source.url, o.id).toMatch(/^https:\/\//)
      for (const s of o.related) expect(s.status, `${o.id} ${s.id}`).toBe('verified')
    }
    expect(verifiedOnly(LIST)).toHaveLength(LIST.length)
    expect(CALENDAR_SOURCE_IDS.length).toBeGreaterThan(OBLIGATION_DATA.length)
  })

  it('holds the dates the official texts state', () => {
    const byId = Object.fromEntries(OBLIGATION_DATA.map((o) => [o.id, o.date]))
    expect(byId['aiact-art50']).toBe('2026-08-02')
    expect(byId['cra-reporting']).toBe('2026-09-11')
    expect(byId['ai-work-decree']).toBe('2026-10-23')
    expect(byId['aiact-legacy-marking']).toBe('2026-12-02')
    expect(byId['aiact-new-prohibitions']).toBe('2026-12-02')
    expect(byId['eudr-application']).toBe('2026-12-30')
    expect(byId['nis2-csirt-contact-2026']).toBe('2026-12-31')
    expect(byId['csrd-first-year']).toBe('2027-01-01')
    expect(byId['nis2-incidents-2026']).toBe('2027-01-01')
    expect(byId['machinery-application']).toBe('2027-01-20')
    expect(byId['nis2-registration']).toBe('2027-02-28')
    expect(byId['omnibus-transposition']).toBe('2027-03-19')
    expect(byId['nis2-annual-update']).toBe('2027-05-31')
    expect(byId['pay-gap-first-data']).toBe('2027-06-07')
    expect(byId['eudr-small-operators']).toBe('2027-06-30')
    expect(byId['nis2-activities-list']).toBe('2027-06-30')
    expect(byId['csddd-guidelines']).toBe('2027-07-26')
    expect(byId['nis2-measures-2026']).toBe('2027-07-31')
    expect(byId['aiact-high-risk-annex-iii']).toBe('2027-12-02')
    expect(byId['cra-full-application']).toBe('2027-12-11')
    expect(byId['csddd-transposition']).toBe('2028-07-26')
    expect(byId['csddd-first-compliance']).toBe('2029-07-26')
  })

  it('speaks the language of the interface with the official act names', () => {
    const entry = obligations(en).find((o) => o.id === 'aiact-art50')
    expect(entry?.title).toBe('AI Act: transparency obligations of Art. 50')
    expect(entry?.source.act).toBe('Regulation (EU) 2024/1689 (AI Act)')
    expect(entry?.source.article).toBe('Art. 113, second paragraph')
    expect(entry?.source.url).toContain('/legal-content/EN/')
    const italian = LIST.find((o) => o.id === 'aiact-art50')
    expect(italian?.source.act).toBe('Regolamento (UE) 2024/1689 (AI Act)')
    expect(italian?.source.quote).toBe('Si applica a decorrere dal 2 agosto 2026')
  })

  it('shows nothing internal: no guide, no file path, no pending note, in either language', () => {
    for (const ctx of [it_, en]) {
      for (const o of obligations(ctx)) {
        const text = `${o.title} ${o.who} ${o.what}`
        expect(text, o.id).not.toMatch(/\bCodex\b|\bADR-?\d|\bprompts?\b|\.planning|riga \d|\.txt|\.tsx?\b|da confermare|to be confirmed|non confermat|not confirmed/i)
      }
    }
  })
})

describe('upcoming', () => {
  it('returns the verified entries of the next twelve months, ascending', () => {
    const list = upcoming(TODAY, 365, LIST)
    expect(list.map((o) => o.id)).toEqual([
      'aiact-legacy-marking',
      'aiact-new-prohibitions',
      'eudr-application',
      'nis2-csirt-contact-2026',
      'csrd-first-year',
      'nis2-incidents-2026',
      'machinery-application',
      'nis2-registration',
      'omnibus-transposition',
      'nis2-annual-update',
      'pay-gap-first-data',
      'eudr-small-operators',
      'nis2-activities-list',
      'csddd-guidelines',
      'nis2-measures-2026',
      'aiact-gpai-legacy',
    ])
    const dates = list.map((o) => o.date)
    expect([...dates].sort()).toEqual(dates)
  })
  it('is inclusive at both ends of the window', () => {
    expect(upcoming(new Date(2026, 11, 2), 0, LIST).map((o) => o.id)).toEqual(['aiact-legacy-marking', 'aiact-new-prohibitions'])
    expect(upcoming(new Date(2026, 11, 29), 1, LIST).map((o) => o.id)).toEqual(['eudr-application'])
    expect(upcoming(new Date(2026, 11, 3), 10, LIST)).toHaveLength(0)
  })
  it('does not include the day before the window starts', () => {
    const list = upcoming(new Date(2026, 9, 24), 365, LIST)
    expect(list.map((o) => o.id)).not.toContain('ai-work-decree')
  })
})

describe('past', () => {
  it('returns entries before today, most recent first', () => {
    const list = past(TODAY, LIST)
    expect(list.map((o) => o.id)).toEqual([
      'ai-work-decree',
      'cra-reporting',
      'aiact-art50',
      'aiact-gpai',
      'aiact-art4-art5',
      'dora-application',
      'nis2-application',
    ])
    expect(list.every((o) => isPast(o, TODAY))).toBe(true)
  })
})

describe('groupByMonth', () => {
  it('groups the next twelve months by month in order', () => {
    const groups = groupByMonth(upcoming(TODAY, 365, LIST))
    expect(groups.map((g) => g.key)).toEqual(['2026-12', '2027-01', '2027-02', '2027-03', '2027-05', '2027-06', '2027-07', '2027-08'])
    expect(groups[0].items.map((o) => o.id)).toEqual([
      'aiact-legacy-marking',
      'aiact-new-prohibitions',
      'eudr-application',
      'nis2-csirt-contact-2026',
    ])
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
