import { describe, it, expect } from 'vitest'
import { answerToPlainText, parseAnswer, resolverFor } from '../answer-text'
import { buildCopyText } from '../copy'
import { formatItalianDate } from '../dates'

const citations = [
  { framework: 'AI_ACT', reference: 'art. 9, par. 1', quote_snippet: 'a' },
  { framework: 'GDPR', reference: 'Art. 22(1)', quote_snippet: 'b' },
  { framework: 'GDPR', reference: 'Art. 9(1)', quote_snippet: 'c' },
]

describe('resolverFor', () => {
  const resolve = resolverFor(citations)

  it('resolves numeric markers within range', () => {
    expect(resolve('1')).toBe(1)
    expect(resolve('3')).toBe(3)
    expect(resolve('4')).toBeNull()
  })

  it('resolves "[framework, reference]" markers', () => {
    expect(resolve('GDPR, Art. 22(1)')).toBe(2)
    expect(resolve('AI Act, Art. 9(1)')).toBe(1)
    expect(resolve('GDPR, Art. 22')).toBe(2)
  })

  it('leaves ambiguous references unresolved', () => {
    expect(resolve('Art. 9')).toBeNull()
    expect(resolve('Art. 9(1)')).toBeNull()
  })
})

describe('parseAnswer', () => {
  it('splits paragraphs, lists, bold runs and markers', () => {
    const text = 'Prima riga **in grassetto** [1].\n\n1. uno [GDPR, Art. 22(1)]\n2. due\n\n- punto'
    const blocks = parseAnswer(text, resolverFor(citations))
    expect(blocks).toHaveLength(3)
    expect(blocks[0]).toEqual({
      type: 'paragraph',
      inline: [
        { type: 'text', text: 'Prima riga ' },
        { type: 'strong', text: 'in grassetto' },
        { type: 'text', text: ' ' },
        { type: 'marker', label: '1', index: 1 },
        { type: 'text', text: '.' },
      ],
    })
    expect(blocks[1]).toMatchObject({ type: 'list', ordered: true })
    expect((blocks[1] as { items: unknown[] }).items).toHaveLength(2)
    expect(blocks[2]).toMatchObject({ type: 'list', ordered: false })
  })

  it('keeps unknown brackets as text', () => {
    const blocks = parseAnswer('Vedi [DORA, Art. 6-16].')
    expect(blocks[0]).toEqual({
      type: 'paragraph',
      inline: [
        { type: 'text', text: 'Vedi ' },
        { type: 'marker', label: 'DORA, Art. 6-16', index: null },
        { type: 'text', text: '.' },
      ],
    })
  })
})

describe('copy text', () => {
  it('strips bold and lists the sources with their status', () => {
    expect(answerToPlainText('**Sì**, vale [1].')).toBe('Sì, vale [1].')
    const text = buildCopyText({
      answer: 'Risposta [1].',
      sources: [
        { id: 'a-1', index: 1, act: 'Regolamento (UE) 2024/1689 (AI Act)', article: 'art. 50, par. 1', quote: 'siano informate', status: 'verified', url: 'https://eur-lex.europa.eu/x' },
        { id: 'a-2', index: 2, act: 'Direttiva (UE) 2026/470 (Omnibus I)', status: 'unverified' },
      ],
      corpusAsOf: '2026-02-28',
      demo: true,
    })
    expect(text).toContain('Fonti\n1. Regolamento (UE) 2024/1689 (AI Act), art. 50, par. 1: «siano informate» (verificata) https://eur-lex.europa.eu/x')
    expect(text).toContain('2. Direttiva (UE) 2026/470 (Omnibus I) (da verificare)')
    expect(text).toContain('Corpus al 28 febbraio 2026 (dati di esempio).')
  })
})

describe('formatItalianDate', () => {
  it('formats ISO dates as Italian long dates and leaves the rest alone', () => {
    expect(formatItalianDate('2026-10-01')).toBe('1 ottobre 2026')
    expect(formatItalianDate('2026-02-28T10:00:00Z')).toBe('28 febbraio 2026')
    expect(formatItalianDate('')).toBeUndefined()
    expect(formatItalianDate(undefined)).toBeUndefined()
    expect(formatItalianDate('Q4 2026')).toBe('Q4 2026')
  })
})
