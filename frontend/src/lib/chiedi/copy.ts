import type { Source } from '@/lib/sources'
import { answerToPlainText } from './answer-text'
import { formatItalianDate } from './dates'

const STATUS_WORD: Record<Source['status'], string> = {
  verified: 'verificata',
  unverified: 'da verificare',
  pending: 'in verifica',
}

/** The answer plus its numbered sources, as plain text for the clipboard. */
export function buildCopyText(opts: {
  answer: string
  sources: Source[]
  corpusAsOf?: string
  demo?: boolean
}): string {
  const lines: string[] = [answerToPlainText(opts.answer)]
  if (opts.sources.length) {
    lines.push('', 'Fonti')
    for (const s of opts.sources) {
      let line = `${s.index}. ${s.act}`
      if (s.article) line += `, ${s.article}`
      if (s.quote) line += `: «${s.quote}»`
      line += ` (${STATUS_WORD[s.status]})`
      if (s.url) line += ` ${s.url}`
      lines.push(line)
    }
  }
  let notice = 'Risposta generata da un sistema di IA (NormaAI).'
  const date = formatItalianDate(opts.corpusAsOf)
  if (date) notice += ` Corpus al ${date}${opts.demo ? ' (dati di esempio)' : ''}.`
  lines.push('', notice)
  return lines.join('\n')
}

/** Copy to the clipboard; false when the browser refuses (no secure context, no permission). */
export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    /* fall through */
  }
  return false
}
