import { formatCorpusDate } from '@/i18n/format'
import type { TextContext } from '@/i18n/types'
import { answerToPlainText } from './answer-text'
import { withActNames, type ChiediSource } from './sources'

/** The answer plus its numbered sources, as plain text for the clipboard. */
export function buildCopyText(
  opts: {
    answer: string
    sources: ChiediSource[]
    corpusAsOf?: string
    demo?: boolean
  },
  ctx: TextContext,
): string {
  const { t } = ctx
  const lines: string[] = [withActNames(answerToPlainText(opts.answer), t)]
  if (opts.sources.length) {
    lines.push('', t('chiedi.copy.sources'))
    for (const s of opts.sources) {
      let line = `${s.index}. ${s.act}`
      if (s.article) line += `, ${s.article}`
      // A quote that differs from the official text travels with the official wording next to it;
      // a quote found elsewhere, with the place where it is.
      const quoted = s.quote || s.near?.quoted || s.elsewhere?.quote
      if (quoted) line += `: «${quoted}»`
      const status = t(`chiedi.copy.status.${s.status}`)
      if (s.near) line += ` (${status}; ${t('chiedi.copy.near', { official: s.near.official })})`
      else if (s.elsewhere) line += ` (${status}; ${t('chiedi.elsewhere.copy', { location: s.elsewhere.location })})`
      else line += ` (${status})`
      if (s.url) line += ` ${s.url}`
      lines.push(line)
    }
  }
  let notice = t('chiedi.copy.notice')
  const date = formatCorpusDate(opts.corpusAsOf, ctx.locale)
  if (date) notice += ' ' + t(opts.demo ? 'chiedi.copy.corpusDemo' : 'chiedi.copy.corpus', { date })
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
