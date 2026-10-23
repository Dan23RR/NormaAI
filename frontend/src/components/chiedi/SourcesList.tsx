'use client'

import { useTranslations } from 'next-intl'
import type { Source } from '@/lib/sources'
import { SourceRow } from '@/components/ui/LawQuote'

/** The numbered sources of one answer, each a button that leads back to its marker. */
export function SourcesList({
  sources,
  activeIndex,
  onSelect,
  label,
}: {
  sources: Source[]
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
        </li>
      ))}
    </ol>
  )
}
