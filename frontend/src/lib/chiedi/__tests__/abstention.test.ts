import { describe, it, expect } from 'vitest'
import { detectAbstention } from '../abstention'

describe('detectAbstention', () => {
  it('trusts the backend flag', () => {
    const r = detectAbstention({
      answer: 'Non posso fornire una risposta sufficientemente affidabile su questa domanda.',
      citations: [],
      abstention_reason: 'snc_low_trust',
    })
    expect(r.abstained).toBe(true)
    expect(r.code).toBe('snc_low_trust')
    expect(r.reason).toContain('Non posso fornire')
  })

  it('recognises the fixed sentence of the Q&A prompt when there are no citations', () => {
    expect(
      detectAbstention({
        answer:
          "I don't have sufficient information in my regulatory database to answer this question with confidence. I recommend consulting a qualified legal professional.",
        citations: [],
      }).abstained,
    ).toBe(true)
    expect(
      detectAbstention({ answer: 'Non ho informazioni sufficienti nella banca dati normativa per rispondere.', citations: [] }).code,
    ).toBe('no_evidence')
  })

  it('does not abstain when the answer carries citations', () => {
    expect(
      detectAbstention({
        answer: 'Non posso fornire una risposta su X, ma su Y la norma dice...',
        citations: [{ framework: 'GDPR', reference: 'art. 6', quote_snippet: 'x' }],
      }).abstained,
    ).toBe(false)
  })

  it('does not abstain on a normal answer without citations', () => {
    expect(detectAbstention({ answer: 'La direttiva si applica dal 2026.', citations: [] }).abstained).toBe(false)
    expect(detectAbstention(undefined).abstained).toBe(false)
  })
})
