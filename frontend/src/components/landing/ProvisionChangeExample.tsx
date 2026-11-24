import { AlertTriangle, ExternalLink } from 'lucide-react'
import { useFormatter, useLocale, useTranslations } from 'next-intl'
import { eurlexLang, languageOf } from '@/i18n/config'
import { LONG_DATE, isoToUtcDate } from '@/i18n/format'
import { AI_ACT_IN_FORCE, CHANGED_PROVISION, EXAMPLES_CHECKED_ON } from '@/lib/landing-examples'
import { eurlexUrl } from '@/lib/sources'

/**
 * A provision that really changed: Article 4 of Regulation (EU) 2024/1689,
 * as adopted and in the text consolidated on 27 July 2026. A document dated
 * before the change and quoting the earlier words is what the document check
 * reports as an outdated quote (src/lib/landing-examples.ts has the record).
 *
 * Only the text in force gets the highlighter: it is what the law says now.
 */
export function ProvisionChangeExample() {
  const t = useTranslations('landing.watch.example')
  const tu = useTranslations('ui')
  const format = useFormatter()
  const locale = useLocale()
  const language = languageOf(locale)
  const example = CHANGED_PROVISION[language]

  const longDate = (iso: string) => {
    const date = isoToUtcDate(iso)
    return date ? format.dateTime(date, LONG_DATE) : iso
  }
  const consolidatedOn = longDate(AI_ACT_IN_FORCE.asOf ?? '')
  const url = eurlexUrl(AI_ACT_IN_FORCE.celex, eurlexLang(locale))

  return (
    <figure aria-label={t('label')} className="rounded-lg border border-rule bg-surface">
      <figcaption className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-rule px-5 py-3 text-caption text-ink-3">
        <span>{t('caption')}</span>
        <span>{t('checkedOn', { date: longDate(EXAMPLES_CHECKED_ON) })}</span>
      </figcaption>

      <div className="px-5 py-5">
        <p className="flex items-start gap-2 text-small font-medium text-bad">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          {t('outdated')}
        </p>
        <p className="mt-1 pl-6 text-small text-ink-2">
          {t('message', { documentDate: longDate(example.documentDate), date: consolidatedOn })}
        </p>

        <p className="mt-5 text-small text-ink-3">{t('inDocument')}</p>
        <blockquote
          lang={language}
          className="mt-1.5 border-l-2 border-rule-2 pl-4 font-serif text-read leading-relaxed text-ink-2"
        >
          {example.before}
        </blockquote>

        <p className="mt-5 text-small text-ink-3">{t('inForce')}</p>
        <figure className="mt-1.5 border-l-2 border-mark-deep pl-4">
          <blockquote lang={language} cite={url} className="font-serif text-read leading-relaxed text-ink">
            <mark>{example.now}</mark>
          </blockquote>
          <figcaption className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-small text-ink-2">
            <span>
              <span className="font-medium text-ink">{tu('acts.AI_ACT')}</span>, {t('article')}
            </span>
            <span>{t('consolidated', { date: consolidatedOn })}</span>
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-union hover:underline"
            >
              EUR-Lex
              <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
            </a>
          </figcaption>
        </figure>
        <p className="mt-4 text-small text-ink-2">{t('replacedBy')}</p>
      </div>
    </figure>
  )
}
