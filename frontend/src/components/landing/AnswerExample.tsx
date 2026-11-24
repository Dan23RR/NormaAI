import type { ReactNode } from 'react'
import { useFormatter, useLocale, useTranslations } from 'next-intl'
import { LawQuote } from '@/components/ui/LawQuote'
import { eurlexLang, languageOf } from '@/i18n/config'
import { LONG_DATE, isoToUtcDate } from '@/i18n/format'
import {
  AI_ACT_APPLIES_FROM,
  AI_ACT_IN_FORCE,
  ANSWER_DATE_PASSAGE,
  ANSWER_PASSAGE,
  EXAMPLES_CHECKED_ON,
} from '@/lib/landing-examples'
import { eurlexUrl } from '@/lib/sources'

/**
 * An answer as the Ask page shows it: the words of the answer, then the two
 * passages it rests on, each with the act, the article and the link to the
 * official text. Both passages are marked as verified because the document
 * check found them word for word in the text consolidated on 27 July 2026,
 * on the date shown (src/lib/landing-examples.ts has the record).
 */
export function AnswerExample() {
  const t = useTranslations('landing.ask.example')
  const tu = useTranslations('ui')
  const format = useFormatter()
  const locale = useLocale()
  const language = languageOf(locale)

  const longDate = (iso: string) => {
    const date = isoToUtcDate(iso)
    return date ? format.dateTime(date, LONG_DATE) : iso
  }
  const checkedOn = longDate(EXAMPLES_CHECKED_ON)
  const act = tu('acts.AI_ACT')
  const url = eurlexUrl(AI_ACT_IN_FORCE.celex, eurlexLang(locale))
  const sources = [
    { passage: ANSWER_PASSAGE[language], article: t('article1') },
    { passage: ANSWER_DATE_PASSAGE[language], article: t('article2') },
  ]
  const ref = (n: number) => (chunks: ReactNode) => (
    <a href={`#esempio-fonte-${n}`} className="font-medium tabular text-union">
      {chunks}
    </a>
  )

  return (
    <figure aria-label={t('label')} className="rounded-lg border border-rule bg-surface">
      <figcaption className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-rule px-5 py-3 text-caption text-ink-3">
        <span>{t('caption')}</span>
        <span>{t('checkedOn', { date: checkedOn })}</span>
      </figcaption>

      <div className="px-5 py-5">
        <p className="text-small text-ink-3">{t('questionLabel')}</p>
        <p className="mt-1 text-read text-ink">{t('question')}</p>
        <p className="mt-5 text-small text-ink-3">{t('answerLabel')}</p>
        <p className="mt-1 text-read text-ink">
          {t.rich('answer', { date: longDate(AI_ACT_APPLIES_FROM), ref1: ref(1), ref2: ref(2) })}
        </p>

        <ol className="mt-5 space-y-5 border-t border-rule pt-5">
          {sources.map(({ passage, article }, i) => (
            <li key={article} id={`esempio-fonte-${i + 1}`} className="flex scroll-mt-24 gap-3">
              <span className="text-small font-medium tabular text-ink-2">[{i + 1}]</span>
              <LawQuote
                className="min-w-0 flex-1"
                quote={passage.quote}
                before={passage.before}
                lang={passage.lang}
                act={act}
                article={article}
                url={url}
                origin="EUR-Lex"
                status="verified"
                verifiedAt={checkedOn}
              />
            </li>
          ))}
        </ol>
      </div>
    </figure>
  )
}
