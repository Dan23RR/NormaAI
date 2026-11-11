'use client'

import { useMemo } from 'react'
import { useTranslations } from 'next-intl'
import { AlertTriangle } from 'lucide-react'
import { SourceRow } from '@/components/ui/LawQuote'
import type { ChiediSource, NearMatch } from '@/lib/chiedi/sources'
import { changedSpan } from '@/lib/word-diff'

/**
 * Under a source whose quote is not in the official text as written: that
 * it differs, how (the words on each side), and the official wording, with
 * the highlighter on the words the answer changed.
 */
export function NearMatchNote({ near }: { near: NearMatch }) {
  const t = useTranslations('chiedi.sources.near')
  const span = useMemo(() => (near.quoted ? changedSpan(near.quoted, near.official) : null), [near.quoted, near.official])
  return (
    <div className="pb-2 pl-10 pr-2">
      <div className="border-l-2 border-warn/60 pl-3">
        <p className="flex items-center gap-1 text-caption font-medium text-warn">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          {t('title')}
        </p>
        {near.quoted && <p className="mt-1 break-words text-caption text-ink-2">{t('quoted', { text: near.quoted })}</p>}
        {near.differences.length > 0 && (
          <ul className="mt-1 space-y-0.5 text-caption text-ink">
            {near.differences.map((difference, index) => (
              <li key={index}>
                {t.rich(difference.quoted && difference.official ? 'both' : difference.official ? 'missing' : 'extra', {
                  quoted: difference.quoted,
                  official: difference.official,
                  w: (chunks) => <span className="font-semibold tabular">{chunks}</span>,
                })}
              </li>
            ))}
          </ul>
        )}
        <p className="mt-1.5 text-caption text-ink-2">{near.article ? t('officialIn', { article: near.article }) : t('official')}</p>
        <p className="mt-0.5 break-words font-serif text-small leading-relaxed text-ink">
          {span ? (
            <>
              {span.before && <span className="text-ink-2">{span.before} </span>}
              <mark>{span.changed}</mark>
              {span.after && <span className="text-ink-2"> {span.after}</span>}
            </>
          ) : (
            <mark>{near.official}</mark>
          )}
        </p>
      </div>
    </div>
  )
}

/** The numbered sources of one answer, each a button that leads back to its marker. */
export function SourcesList({
  sources,
  activeIndex,
  onSelect,
  label,
}: {
  sources: ChiediSource[]
  activeIndex?: number | null
  onSelect?: (index: number) => void
  label: string
}) {
  const t = useTranslations('chiedi.sources')
  if (sources.length === 0) {
    return <p className="text-small text-ink-2">{t('none')}</p>
  }
  return (
    <ol className="space-y-1" aria-label={label}>
      {sources.map((s) => (
        <li key={s.id}>
          <SourceRow source={s} active={activeIndex === s.index} onSelect={onSelect ? () => onSelect(s.index) : undefined} />
          {s.near && <NearMatchNote near={s.near} />}
        </li>
      ))}
    </ol>
  )
}
