import type { Source } from '@/lib/sources'
import { formatCorpusDate } from '@/i18n/format'
import type { TextContext } from '@/i18n/types'
import { answerToPlainText } from './answer-text'

/** The answer plus its numbered sources, as plain text for the clipboard. */
export function buildCopyText(
  opts: {
    answer: string
    sources: Source[]
    corpusAsOf?: string
    demo?: boolean
  },
  ctx: TextContext,
): string {
  const { t } = ctx
  const lines: string[] = [answerToPlainText(opts.answer)]
  if (opts.sources.length) {
    lines.push('', t('chiedi.copy.sources'))
    for (const s of opts.sources) {
      let line = `${s.index}. ${s.act}`
      if (s.article) line += `, ${s.article}`
      if (s.quote) line += `: «${s.quote}»`
      line += ` (${t(`chiedi.copy.status.${s.status}`)})`
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
