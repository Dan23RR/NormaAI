'use client'

import { useLocale, useTranslations } from 'next-intl'
import { ExternalLink } from 'lucide-react'
import { languageOf } from '@/i18n/config'
import { ABSTENTION_CODES } from '@/lib/chiedi/abstention'
import { AiNotice } from './AiNotice'

/**
 * Shown instead of an answer when the backend abstains: the reason, what
 * to do next, and (demo only) example questions the demo does cover.
 */
export function AbstentionNotice({
  code,
  reason,
  suggestions,
  onSuggestion,
  corpusAsOf,
  demo,
}: {
  /** The backend's abstention code, when it sent one. */
  code?: string
  /** The explanation the backend wrote, when the answer text is the reason. */
  reason?: string
  suggestions?: string[]
  onSuggestion?: (question: string) => void
  corpusAsOf?: string
  demo?: boolean
}) {
  const t = useTranslations('chiedi.abstention')
  const locale = useLocale()
  const known = code && (ABSTENTION_CODES as readonly string[]).includes(code) ? code : 'no_evidence'
  const explanation = reason ?? t(`reasons.${known}`)
  return (
    <div className="rounded-lg border border-rule bg-surface-2 px-5 py-5">
      <h3 className="text-h4">{t('title')}</h3>
      {explanation && <p className="mt-2 text-body text-ink-2">{explanation}</p>}
      <p className="mt-3 text-body text-ink">{t('whatToDo')}</p>
      <a
        href={`https://eur-lex.europa.eu/homepage.html?locale=${languageOf(locale)}`}
        target="_blank"
        rel="noopener noreferrer"
        className="mt-2 inline-flex items-center gap-1 text-small font-medium text-union hover:underline"
      >
        {t('openEurlex')}
        <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
      </a>
      {suggestions && suggestions.length > 0 && onSuggestion && (
        <div className="mt-4">
          <p className="text-small text-ink-2">{t('demoQuestions')}</p>
          <ul className="mt-2 flex flex-wrap gap-2" aria-label={t('examples')}>
            {suggestions.map((s) => (
              <li key={s}>
                <button
                  type="button"
                  onClick={() => onSuggestion(s)}
                  className="rounded-md border border-rule-2 bg-surface px-3 py-1.5 text-left text-small text-ink-2 hover:border-union hover:text-ink"
                >
                  {s}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      <AiNotice corpusAsOf={corpusAsOf} demo={demo} className="mt-4" />
    </div>
  )
}
