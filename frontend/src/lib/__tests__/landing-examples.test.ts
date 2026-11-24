import { describe, it, expect } from 'vitest'
// What the document check returned for the example texts, and the official
// paragraphs they quote, as read from CELLAR: written by a script, see `about`.
import record from './fixtures/landing-examples.checked.json'
import { LANGUAGES } from '@/i18n/config'
import {
  AI_ACT_AS_ADOPTED,
  AI_ACT_IN_FORCE,
  ANSWER_DATE_PASSAGE,
  ANSWER_PASSAGE,
  CHANGED_PROVISION,
  CHECKED_NOTE,
  EXAMPLES_CHECKED_ON,
  GDPR_IN_FORCE,
  noteText,
  splitAtWord,
} from '../landing-examples'

interface Finding {
  reference: string
  status: string
  version: string | null
  version_as_of: string | null
  quotes: string[]
  official_quote: string | null
  differences: Array<{ quoted: string; official: string }>
  before_version: string | null
}
interface Check {
  document_date: string | null
  text: string
  findings: Finding[]
}
const checks = record.checks as Record<string, Check>
const passages = record.passages as Record<string, { version: string; text: string }>

describe('the examples of the landing page and the record of their check', () => {
  it('carry the date of the record', () => {
    expect(EXAMPLES_CHECKED_ON).toBe(record.checked_on)
  })

  describe.each(LANGUAGES)('the checked note (%s)', (language) => {
    const note = CHECKED_NOTE[language]
    const check = checks[`note-${language}`]
    const [altered, verified] = check.findings

    it('is the text that was checked', () => {
      expect(noteText(note)).toBe(check.text)
      expect(check.findings).toHaveLength(2)
    })

    it('shows the altered quote as the check reported it', () => {
      expect(altered.status).toBe('alterata')
      expect(altered.reference).toBe(note.altered.reference)
      expect(altered.quotes).toEqual([note.altered.quote])
      expect(altered.official_quote).toBe(note.altered.official)
      expect(altered.differences).toEqual([note.altered.difference])
      expect(altered.version).toBe(GDPR_IN_FORCE.celex)
      expect(altered.version_as_of).toBe(GDPR_IN_FORCE.asOf)
    })

    it('shows the other quote as verified because the check found it word for word', () => {
      expect(verified.status).toBe('verificata')
      expect(verified.reference).toBe(note.verified.reference)
      expect(verified.quotes).toEqual([note.verified.quote])
      expect(verified.version).toBe(GDPR_IN_FORCE.celex)
    })

    it('quotes the official paragraphs literally', () => {
      const first = passages[`gdpr-33-1-${language}`]
      const fifth = passages[`gdpr-33-5-${language}`]
      expect(first.version).toBe(GDPR_IN_FORCE.celex)
      expect(first.text).toContain(note.altered.official)
      expect(first.text).not.toContain(note.altered.quote)
      expect(fifth.text).toContain(note.verified.quote)
    })

    it('differs from the official wording by the one word it flags', () => {
      const { quoted, official } = note.altered.difference
      const inNote = splitAtWord(note.altered.quote, quoted)
      const inLaw = splitAtWord(note.altered.official, official)
      expect(inNote).not.toBeNull()
      expect(inLaw).not.toBeNull()
      expect(inNote?.before).toBe(inLaw?.before)
      expect(inNote?.after).toBe(inLaw?.after)
    })
  })

  describe.each(LANGUAGES)('the provision that changed (%s)', (language) => {
    const example = CHANGED_PROVISION[language]

    it('was reported as an outdated quote for a document of that date', () => {
      const check = checks[`change-before-${language}`]
      const [finding] = check.findings
      expect(check.document_date).toBe(example.documentDate)
      expect(finding.status).toBe('superata')
      expect(finding.quotes).toEqual([example.before])
      expect(finding.version).toBe(AI_ACT_IN_FORCE.celex)
      expect(finding.version_as_of).toBe(AI_ACT_IN_FORCE.asOf)
      expect(finding.before_version).toBe(AI_ACT_AS_ADOPTED.celex)
    })

    it('shows as text in force words the check verified there', () => {
      const [finding] = checks[`change-now-${language}`].findings
      expect(finding.status).toBe('verificata')
      expect(finding.quotes).toEqual([example.now])
      expect(finding.version).toBe(AI_ACT_IN_FORCE.celex)
    })

    it('quotes each version literally, and only that version', () => {
      const adopted = passages[`ai-act-4-as-adopted-${language}`]
      const inForce = passages[`ai-act-4-1-${language}`]
      expect(adopted.version).toBe(AI_ACT_AS_ADOPTED.celex)
      expect(inForce.version).toBe(AI_ACT_IN_FORCE.celex)
      expect(adopted.text).toContain(example.before)
      expect(inForce.text).not.toContain(example.before)
      expect(inForce.text).toContain(example.now)
      expect(adopted.text).not.toContain(example.now)
    })
  })

  describe.each(LANGUAGES)('the passages of the example answer (%s)', (language) => {
    const passage = ANSWER_PASSAGE[language]
    const date = ANSWER_DATE_PASSAGE[language]

    it('were verified in the text in force', () => {
      const [first, second] = checks[`answer-${language}`].findings
      expect(first.status).toBe('verificata')
      expect(first.quotes).toEqual([passage.quote])
      expect(first.version).toBe(AI_ACT_IN_FORCE.celex)
      expect(second.status).toBe('verificata')
      expect(second.quotes).toEqual([date.quote])
      expect(second.version).toBe(AI_ACT_IN_FORCE.celex)
    })

    it('are literal, context included', () => {
      // The page shows the context, a space, then the highlighted words.
      expect(passages[`ai-act-50-1-${language}`].text).toContain(`${passage.before} ${passage.quote}`)
      expect(passages[`ai-act-113-${language}`].text).toContain(date.quote)
      expect(passage.lang).toBe(language)
      expect(date.lang).toBe(language)
    })
  })
})

describe('splitAtWord', () => {
  it('cuts the text around a whole word', () => {
    expect(splitAtWord('entro 48 ore', '48')).toEqual({ before: 'entro ', word: '48', after: ' ore' })
    expect(splitAtWord('48', '48')).toEqual({ before: '', word: '48', after: '' })
  })

  it('skips the same characters inside a longer word or number', () => {
    expect(splitAtWord('articolo 148, entro 48 ore', '48')).toEqual({
      before: 'articolo 148, entro ',
      word: '48',
      after: ' ore',
    })
    expect(splitAtWord('nessuna violazione', 'una')).toBeNull()
    expect(splitAtWord('però', 'per')).toBeNull()
  })

  it('finds nothing for a missing or empty word', () => {
    expect(splitAtWord('entro 72 ore', '48')).toBeNull()
    expect(splitAtWord('entro 72 ore', '')).toBeNull()
  })
})
