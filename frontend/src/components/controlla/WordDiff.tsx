'use client'

import { Fragment, useMemo } from 'react'
import { useTranslations } from 'next-intl'
import { cn } from '@/lib/cn'
import { diffWords, hasChanges } from '@/lib/word-diff'

/** Unchanged stretches longer than this are shortened to their two ends, as in the report. */
const COLLAPSE = { longerThan: 40, keep: 15 }

const REMOVED = 'rounded-sm bg-bad/10 px-0.5 text-ink-2 line-through decoration-bad'
const ADDED = 'rounded-sm bg-ok/10 px-0.5 text-ink underline decoration-ok decoration-2 underline-offset-2'

/**
 * A provision before and after, word by word. Removed words are struck
 * through, added words underlined: the tint helps, but the line is what
 * carries the meaning, and a screen reader hears "tolto" and "aggiunto".
 */
export function WordDiff({ before, after, lang, className }: { before: string; after: string; lang?: string; className?: string }) {
  const t = useTranslations('controlla.diff')
  const segments = useMemo(() => diffWords(before, after, { collapse: COLLAPSE }), [before, after])

  if (!hasChanges(segments)) {
    return <p className={cn('text-small text-ink-2', className)}>{t('same')}</p>
  }

  return (
    <div className={cn('rounded-md border border-rule bg-surface-2 px-4 py-3', className)}>
      <p className="break-words font-serif text-read leading-relaxed text-ink" lang={lang}>
        {segments.map((segment, index) => {
          if (segment.kind === 'equal') return <Fragment key={index}>{segment.text} </Fragment>
          if (segment.kind === 'omitted') {
            const label = t('omitted', { count: segment.count })
            return (
              <Fragment key={index}>
                <span className="font-sans text-small text-ink-2" title={label}>
                  <span aria-hidden="true">[...]</span>
                  <span className="sr-only">{label}</span>
                </span>{' '}
              </Fragment>
            )
          }
          const removed = segment.kind === 'removed'
          const Tag = removed ? 'del' : 'ins'
          return (
            <Fragment key={index}>
              <Tag className={removed ? REMOVED : ADDED}>
                <span className="sr-only">{t(removed ? 'removed' : 'added')} </span>
                {segment.text}
              </Tag>{' '}
            </Fragment>
          )
        })}
      </p>
      <p className="mt-3 text-caption text-ink-2">
        {t.rich('legend', {
          del: (chunks) => <del className={REMOVED}>{chunks}</del>,
          ins: (chunks) => <ins className={ADDED}>{chunks}</ins>,
        })}
      </p>
    </div>
  )
}
