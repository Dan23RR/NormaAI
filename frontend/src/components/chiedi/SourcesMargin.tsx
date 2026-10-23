'use client'

import type { ReactNode } from 'react'
import { useTranslations } from 'next-intl'
import type { Source } from '@/lib/sources'
import { detectAbstention } from '@/lib/chiedi/abstention'
import type { AssistantMessage } from '@/lib/chiedi/types'
import { SourcesList } from './SourcesList'

/**
 * The margin of the annotated code: the sources of the selected answer,
 * fixed while the conversation scrolls. Desktop only; under `lg` each
 * answer carries its own collapsible sources.
 */
export function SourcesMargin({
  message,
  sources,
  activeIndex,
  totalAnswers,
  onSelect,
  children,
}: {
  message: AssistantMessage | undefined
  sources: Source[]
  activeIndex: number | null
  totalAnswers: number
  onSelect: (index: number) => void
  /** Rendered above the sources: the company profile panel. */
  children?: ReactNode
}) {
  const t = useTranslations('chiedi')
  const abstained = message?.data ? detectAbstention(message.data).abstained : false
  const waiting = message && (message.status === 'loading' || message.status === 'streaming') && sources.length === 0

  return (
    <aside aria-label={t('sources.aside')} className="hidden min-w-0 lg:block">
      <div className="sticky top-6 flex max-h-[calc(100vh-3rem)] flex-col gap-5 overflow-y-auto pr-1">
        {children}
        <section aria-labelledby="sources-heading">
          <h2 id="sources-heading" className="text-h4">
            {sources.length > 0 ? t('sources.headingCount', { count: sources.length }) : t('sources.heading')}
          </h2>
          {message && totalAnswers > 1 && (
            <p className="mt-1 truncate text-caption text-ink-3" title={message.question}>
              {t('sources.ofAnswer', { question: message.question })}
            </p>
          )}
          <div className="mt-3">
            {!message ? (
              <p className="text-small text-ink-2">{t('sources.intro')}</p>
            ) : message.status === 'error' ? (
              <p className="text-small text-ink-2">{t('sources.error')}</p>
            ) : waiting ? (
              <p className="text-small text-ink-2">{t('sources.waiting')}</p>
            ) : abstained ? (
              <p className="text-small text-ink-2">{t('sources.abstained')}</p>
            ) : (
              <SourcesList sources={sources} activeIndex={activeIndex} onSelect={onSelect} label={t('answer.sourcesOfAnswer')} />
            )}
          </div>
          {sources.length > 0 && <p className="mt-4 text-caption text-ink-3">{t('sources.legend')}</p>}
        </section>
      </div>
    </aside>
  )
}
