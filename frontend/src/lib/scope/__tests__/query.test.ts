import { describe, it, expect } from 'vitest'
import { EMPTY_INPUT, inputToQuery, queryToInput, keysToAi, NO_AI } from '../query'
import { parseNumber, formatInt, formatEur, formatMillionsEur } from '@/i18n/format'
import { textContextFor } from '@/test/i18n'

describe('parseNumber (port of toNum in public/scope-csrd.html)', () => {
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
    expect(formatEur(450_000_000, 'it-IT')).toBe('450.000.000 €')
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

describe('query string round trip', () => {
  it('keeps every field that was set', () => {
    const input = {
      ...EMPTY_INPUT,
      name: 'Acme Srl',
      employees: 1500,
      turnoverEur: 620_000_000,
      listedEu: true,
      wave1Reporter: true,
      groupRole: 'parent' as const,
      sector: 'Manifattura',
      country: 'IT',
      ai: keysToAi(['chat', 'deep']),
    }
    const q = inputToQuery(input).toString()
    expect(queryToInput(q)).toEqual(input)
  })
  it('encodes "none of the four" as an answered question', () => {
    const q = inputToQuery({ ...EMPTY_INPUT, employees: 10, turnoverEur: 1, ai: NO_AI })
    expect(q.get('ia')).toBe('nessuna')
    expect(queryToInput(q)?.ai).toEqual(NO_AI)
  })
  it('leaves the AI answers null when the key is absent', () => {
    expect(queryToInput('dip=600&ricavi=120000000')?.ai).toBeNull()
  })
  it('returns null for a query with nothing to assess', () => {
    expect(queryToInput('')).toBeNull()
    expect(queryToInput('nome=Acme')).toBeNull()
  })
  it('ignores negative or malformed numbers and unknown AI keys', () => {
    const input = queryToInput('dip=-5&ricavi=abc&ia=chat,bogus')
    expect(input?.employees).toBeNull()
    expect(input?.turnoverEur).toBeNull()
    expect(input?.ai).toEqual(keysToAi(['chat']))
  })
})
