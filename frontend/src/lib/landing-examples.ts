/**
 * The three examples of the landing page: a checked note, a provision that
 * changed, an answer with its passages.
 *
 * The notes are invented. The law is not: every passage below is the official
 * text as CELLAR gave it, and every outcome the page shows is what the
 * document check of this repository (src/document_check) returned for these
 * very texts on EXAMPLES_CHECKED_ON. The record of those checks, written by a
 * script, is src/lib/__tests__/fixtures/landing-examples.checked.json; a test
 * compares this file with it, so an example cannot be edited away from what
 * was checked. To repeat a check, save the text of a note to a file and run
 * `python scripts/check_document.py <file>`.
 *
 * A passage keeps the language of the official text it comes from: the
 * English page quotes the English text of the Official Journal.
 */
import type { Language } from '@/i18n/config'
import { AI_ACT_ART_50_1_IT, type QuotedPassage } from './law-passages'

/** The day the examples went through the document check (ISO). */
export const EXAMPLES_CHECKED_ON = '2026-11-11'

/** A version of an act, as the document check names it. */
export interface TextVersion {
  /** CELEX of the version: a consolidated text ("02016R0679-20160504") or the act as adopted. */
  celex: string
  /** ISO date of a consolidated text; absent for the act as adopted. */
  asOf?: string
}

/** The texts in force on EXAMPLES_CHECKED_ON: the latest consolidated versions in CELLAR. */
export const GDPR_IN_FORCE: TextVersion = { celex: '02016R0679-20160504', asOf: '2016-05-04' }
export const AI_ACT_IN_FORCE: TextVersion = { celex: '02024R1689-20260727', asOf: '2026-07-27' }
export const AI_ACT_AS_ADOPTED: TextVersion = { celex: '32024R1689' }

// ─── A checked note (the hero) ───────────────────────────────────────

export interface CheckedNote {
  title: string
  /** The marks the note puts around the words of the law. */
  marks: readonly [open: string, close: string]
  /** First paragraph: a quote that differs from the official text. */
  altered: {
    before: string
    /** The reference, as the note writes it. */
    reference: string
    between: string
    /** The words the note attributes to the law. */
    quote: string
    after: string
    /** The words that differ, as the check reports them. */
    difference: { quoted: string; official: string }
    /** The official wording the quote almost matched. */
    official: string
  }
  /** Second paragraph: a quote found word for word. */
  verified: {
    before: string
    quote: string
    between: string
    reference: string
    after: string
  }
}

/** Regulation (EU) 2016/679, Article 33(1) and (5), consolidated text of 4 May 2016. */
export const CHECKED_NOTE: Record<Language, CheckedNote> = {
  it: {
    title: 'Nota al cliente: violazioni dei dati personali',
    marks: ['«', '»'],
    altered: {
      before: "In caso di violazione, la notifica al Garante va fatta, come prevede l'",
      reference: 'articolo 33, paragrafo 1, del regolamento (UE) 2016/679',
      between: ', ',
      quote: 'senza ingiustificato ritardo e, ove possibile, entro 48 ore dal momento in cui ne è venuto a conoscenza',
      after: '.',
      difference: { quoted: '48', official: '72' },
      official: 'senza ingiustificato ritardo e, ove possibile, entro 72 ore dal momento in cui ne è venuto a conoscenza',
    },
    verified: {
      before: 'Ogni violazione va annotata nel registro interno: il titolare ',
      quote: 'documenta qualsiasi violazione dei dati personali',
      between: ' (',
      reference: 'articolo 33, paragrafo 5, del regolamento (UE) 2016/679',
      after: ').',
    },
  },
  en: {
    title: 'Client note: personal data breaches',
    marks: ['"', '"'],
    altered: {
      before: 'If a breach occurs, the supervisory authority must be notified, as ',
      reference: 'Article 33(1) of Regulation (EU) 2016/679',
      between: ' provides, ',
      quote: 'without undue delay and, where feasible, not later than 48 hours after having become aware of it',
      after: '.',
      difference: { quoted: '48', official: '72' },
      official: 'without undue delay and, where feasible, not later than 72 hours after having become aware of it',
    },
    verified: {
      before: 'Every breach goes into the internal register: the controller ',
      quote: 'shall document any personal data breaches',
      between: ' (',
      reference: 'Article 33(5) of Regulation (EU) 2016/679',
      after: ').',
    },
  },
}

/** The note as plain text, one paragraph per line group: what went through the check. */
export function noteText(note: CheckedNote): string {
  const [open, close] = note.marks
  const { altered: a, verified: v } = note
  return [
    note.title,
    `${a.before}${a.reference}${a.between}${open}${a.quote}${close}${a.after}`,
    `${v.before}${open}${v.quote}${close}${v.between}${v.reference}${v.after}`,
  ]
    .map((paragraph) => `${paragraph}\n`)
    .join('\n')
}

/** Digits and Latin letters, accented ones included: what a word of these texts is made of. */
const WORD_CHAR = /[0-9A-Za-zÀ-ɏ]/

/** `text` cut around the first occurrence of `word` that stands as a whole word. */
export function splitAtWord(text: string, word: string): { before: string; word: string; after: string } | null {
  if (!word) return null
  for (let i = text.indexOf(word); i >= 0; i = text.indexOf(word, i + 1)) {
    const end = i + word.length
    const inside = (i > 0 && WORD_CHAR.test(text[i - 1])) || (end < text.length && WORD_CHAR.test(text[end]))
    if (!inside) return { before: text.slice(0, i), word, after: text.slice(end) }
  }
  return null
}

// ─── A provision that changed (watching) ─────────────────────────────

export interface ChangedProvision {
  /** ISO date of the invented document that quotes the earlier wording. */
  documentDate: string
  /** The words of the act as adopted, which the document quotes. */
  before: string
  /** The words that replaced them in the text in force. */
  now: string
}

/**
 * Regulation (EU) 2024/1689, Article 4: the act as adopted and the text
 * consolidated on 27 July 2026, after Regulation (EU) 2026/1744 replaced the
 * article (its Article 1, point 5).
 */
export const CHANGED_PROVISION: Record<Language, ChangedProvision> = {
  it: {
    documentDate: '2026-03-15',
    before:
      'adottano misure per garantire nella misura del possibile un livello sufficiente di alfabetizzazione in materia di IA del loro personale',
    now: "adottano misure volte a sostenere lo sviluppo dell'alfabetizzazione in materia di IA del loro personale",
  },
  en: {
    documentDate: '2026-03-15',
    before: 'shall take measures to ensure, to their best extent, a sufficient level of AI literacy of their staff',
    now: 'shall take measures to support the development of AI literacy of their staff',
  },
}

// ─── An answer with its passages (asking) ────────────────────────────

/** Regulation (EU) 2024/1689, Article 50(1), text consolidated on 27 July 2026. */
export const ANSWER_PASSAGE: Record<Language, QuotedPassage> = {
  it: { before: AI_ACT_ART_50_1_IT.before, quote: AI_ACT_ART_50_1_IT.quote, lang: 'it', celex: '32024R1689' },
  en: {
    before:
      'Providers shall ensure that AI systems intended to interact directly with natural persons are designed and developed in such a way that the natural persons concerned',
    quote: 'are informed that they are interacting with an AI system',
    lang: 'en',
    celex: '32024R1689',
  },
}

/** Regulation (EU) 2024/1689, Article 113, second paragraph, same text. */
export const ANSWER_DATE_PASSAGE: Record<Language, QuotedPassage> = {
  it: { quote: 'Si applica a decorrere dal 2 agosto 2026.', lang: 'it', celex: '32024R1689' },
  en: { quote: 'It shall apply from 2 August 2026.', lang: 'en', celex: '32024R1689' },
}

/** 2 August 2026: the date Article 113 gives, as the example answer states it. */
export const AI_ACT_APPLIES_FROM = '2026-08-02'
