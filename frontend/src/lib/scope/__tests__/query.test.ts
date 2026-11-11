import { describe, it, expect } from 'vitest'
import {
  EMPTY_INPUT,
  NO_AI,
  NO_MACHINERY,
  NO_NIS,
  NO_WORK_AI,
  inputToQuery,
  keysToAi,
  keysToMachinery,
  keysToWork,
  machineryToKeys,
  queryToInput,
  workToKeys,
} from '../query'
import { parseNumber, formatInt, formatEur, formatMillionsEur } from '@/i18n/format'
import { textContextFor } from '@/test/i18n'

describe('parseNumber', () => {
  it('reads Italian thousands separators', () => {
    expect(parseNumber('1.200', 'it-IT')).toBe(1200)
    expect(parseNumber('450.000.000', 'it-IT')).toBe(450_000_000)
  })
  it('reads a decimal comma and a short decimal point', () => {
    expect(parseNumber('1,5', 'it-IT')).toBe(1.5)
    expect(parseNumber('12.5', 'it-IT')).toBe(12.5)
  })
  it('reads plain digits, spaces and euro signs', () => {
    expect(parseNumber('1200', 'it-IT')).toBe(1200)
    expect(parseNumber(' 620 000 000 € ', 'it-IT')).toBe(620_000_000)
  })
  it('reads English notation when the interface is English', () => {
    expect(parseNumber('1,200', 'en-GB')).toBe(1200)
    expect(parseNumber('450,000,000', 'en-GB')).toBe(450_000_000)
    expect(parseNumber('1.5', 'en-GB')).toBe(1.5)
    expect(parseNumber('1200', 'en-GB')).toBe(1200)
  })
  it('returns null for empty or non-numeric input', () => {
    expect(parseNumber('', 'it-IT')).toBeNull()
    expect(parseNumber('abc', 'it-IT')).toBeNull()
    expect(parseNumber(null, 'it-IT')).toBeNull()
  })
})

describe('formatting', () => {
  it('uses the separators of the locale', () => {
    expect(formatInt(1200, 'it-IT')).toBe('1.200')
    // Intl keeps the euro sign on the same line as the amount (no-break space).
    expect(formatEur(450_000_000, 'it-IT')).toBe('450.000.000\u00a0€')
    expect(formatInt(1200, 'en-GB')).toBe('1,200')
    expect(formatEur(450_000_000, 'en-GB')).toBe('€450,000,000')
  })
  it('writes millions and billions in words', () => {
    const it_ = textContextFor('it')
    expect(formatMillionsEur(450_000_000, it_)).toBe('450 milioni di euro')
    expect(formatMillionsEur(1_500_000_000, it_)).toBe('1,5 miliardi di euro')
    expect(formatMillionsEur(1_000_000, it_)).toBe('1 milione di euro')
    const en = textContextFor('en')
    expect(formatMillionsEur(450_000_000, en)).toBe('450 million euro')
    expect(formatMillionsEur(1_500_000_000, en)).toBe('1.5 billion euro')
  })
})

describe('answer keys', () => {
  it('turn into answers and back for each group', () => {
    expect(workToKeys(keysToWork(['dec', 'emo']))).toEqual(['dec', 'emo'])
    expect(keysToWork([])).toEqual(NO_WORK_AI)
    expect(machineryToKeys(keysToMachinery(['imp', 'mod']))).toEqual(['imp', 'mod'])
    expect(keysToMachinery([])).toEqual(NO_MACHINERY)
    expect(keysToAi([])).toEqual(NO_AI)
  })
})

describe('query string round trip', () => {
  it('keeps every field that was set', () => {
    const input = {
      ...EMPTY_INPUT,
      name: 'Acme Srl',
      employees: 1500,
      turnoverEur: 620_000_000,
      balanceSheetEur: 410_000_000,
      listedEu: true,
      wave1Reporter: true,
      groupRole: 'parent' as const,
      sector: 'Manifattura',
      country: 'IT',
      ai: keysToAi(['chat', 'deep']),
      work: keysToWork(['dec', 'uso']),
      nis: { sector: 'fabbricazione' as const, anySize: false, linked: true },
      machinery: keysToMachinery(['fab', 'mod']),
    }
    const q = inputToQuery(input).toString()
    expect(queryToInput(q)).toEqual(input)
  })
  it('keeps a company outside the EU with its turnover in the Union', () => {
    const input = { ...EMPTY_INPUT, nonEu: true, euTurnoverEur: 500_000_000 }
    expect(queryToInput(inputToQuery(input))).toEqual(input)
  })
  it('encodes "none of these" as an answered question in every group', () => {
    const q = inputToQuery({ ...EMPTY_INPUT, ai: NO_AI, work: NO_WORK_AI, nis: NO_NIS, machinery: NO_MACHINERY })
    expect(q.get('ia')).toBe('nessuna')
    expect(q.get('lav')).toBe('nessuna')
    expect(q.get('nis')).toBe('nessuno')
    expect(q.get('mac')).toBe('nessuna')
    const back = queryToInput(q)
    expect(back?.ai).toEqual(NO_AI)
    expect(back?.work).toEqual(NO_WORK_AI)
    expect(back?.nis).toEqual(NO_NIS)
    expect(back?.machinery).toEqual(NO_MACHINERY)
  })
  it('leaves a group null when its key is absent: unanswered is never read as "none"', () => {
    const input = queryToInput('dip=600&ricavi=120000000')
    expect(input?.ai).toBeNull()
    expect(input?.work).toBeNull()
    expect(input?.nis).toBeNull()
    expect(input?.machinery).toBeNull()
    expect(input?.balanceSheetEur).toBeNull()
  })
  it('assesses a query that carries only one of the new sections', () => {
    expect(queryToInput('mac=fab')?.machinery).toEqual(keysToMachinery(['fab']))
    expect(queryToInput('lav=prof')?.work).toEqual(keysToWork(['prof']))
    expect(queryToInput('nis=energia&nisdim=1')?.nis).toEqual({ sector: 'energia', anySize: true, linked: false })
  })
  it('returns null for a query with nothing to assess', () => {
    expect(queryToInput('')).toBeNull()
    expect(queryToInput('nome=Acme')).toBeNull()
    expect(queryToInput('bilancio=12000000')).toBeNull()
  })
  it('ignores negative or malformed numbers, unknown keys and unknown sectors', () => {
    const input = queryToInput('dip=-5&ricavi=abc&bilancio=x&ia=chat,bogus&lav=dec,boh&mac=zzz&nis=agricoltura')
    expect(input?.employees).toBeNull()
    expect(input?.turnoverEur).toBeNull()
    expect(input?.balanceSheetEur).toBeNull()
    expect(input?.ai).toEqual(keysToAi(['chat']))
    expect(input?.work).toEqual(keysToWork(['dec']))
    expect(input?.machinery).toEqual(NO_MACHINERY)
    expect(input?.nis).toBeNull()
  })
})
