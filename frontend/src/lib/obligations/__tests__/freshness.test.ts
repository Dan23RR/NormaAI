import { describe, it, expect } from 'vitest'
import { freshnessLine, readFreshness } from '../freshness'
import { textContextFor } from '@/test/i18n'

const it_ = textContextFor('it')
const en = textContextFor('en')

const OUTDATED = { celex: '32024R1689', indexed: '02024R1689-20260727', latest: '02024R1689-20261202' }

describe('readFreshness', () => {
  it('is undefined when the stats carry no freshness (older backend, demo)', () => {
    expect(readFreshness({ status: 'healthy', version: '2.0.0' })).toBeUndefined()
    expect(readFreshness({})).toBeUndefined()
    expect(readFreshness(null)).toBeUndefined()
    expect(readFreshness(undefined)).toBeUndefined()
    expect(readFreshness({ freshness: 'ieri' })).toBeUndefined()
    expect(readFreshness({ freshness: { checked_at: 20261111 } })).toBeUndefined()
  })

  it('reads the date of the last run and the acts with a newer consolidated version', () => {
    expect(readFreshness({ freshness: { checked_at: '2026-11-11T02:10:00Z', outdated: [OUTDATED] } })).toEqual({
      checkedAt: '2026-11-11T02:10:00Z',
      outdated: [OUTDATED],
    })
  })

  it('keeps a check that never ran apart from a missing one, and drops malformed rows', () => {
    expect(readFreshness({ freshness: { checked_at: null, outdated: [] } })).toEqual({ checkedAt: null, outdated: [] })
    expect(readFreshness({ freshness: { checked_at: '  ' } })).toEqual({ checkedAt: null, outdated: [] })
    expect(
      readFreshness({ freshness: { checked_at: '2026-11-11T02:10:00Z', outdated: [OUTDATED, { celex: 'x' }, null, 'y'] } })?.outdated,
    ).toEqual([OUTDATED])
  })
})

describe('freshnessLine', () => {
  it('says the calendar is curated by hand when the server reports no automatic check', () => {
    const line = freshnessLine(undefined, it_)
    expect(line).toMatch(/^Calendario curato a mano/)
    expect(line).toContain('non riporta un controllo automatico')
    expect(freshnessLine(undefined, en)).toMatch(/^Hand-curated calendar/)
  })

  it('says so when the check exists but never ran', () => {
    expect(freshnessLine({ checkedAt: null, outdated: [] }, it_)).toContain('non è ancora stato eseguito')
    expect(freshnessLine({ checkedAt: null, outdated: [] }, en)).toContain('has not run yet')
  })

  it('says when the check last ran and how many indexed acts have a newer consolidated version', () => {
    const at = '2026-11-11T02:10:00Z'
    expect(freshnessLine({ checkedAt: at, outdated: [] }, it_)).toBe(
      "Calendario curato a mano. Controllo automatico delle versioni consolidate eseguito l’11 novembre 2026: nessun atto indicizzato ha una versione consolidata più recente.",
    )
    expect(freshnessLine({ checkedAt: at, outdated: [OUTDATED] }, it_)).toContain(
      '1 atto indicizzato ha una versione consolidata più recente',
    )
    expect(freshnessLine({ checkedAt: '2026-12-02T02:10:00Z', outdated: [OUTDATED, OUTDATED, OUTDATED] }, it_)).toContain(
      'eseguito il 2 dicembre 2026: 3 atti indicizzati hanno una versione consolidata più recente',
    )
    expect(freshnessLine({ checkedAt: at, outdated: [OUTDATED, OUTDATED] }, en)).toBe(
      'Hand-curated calendar. Automatic check of consolidated versions last run on 11 November 2026: 2 indexed acts have a newer consolidated version.',
    )
  })
})
