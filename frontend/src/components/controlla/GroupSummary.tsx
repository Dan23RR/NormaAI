'use client'

import { useTranslations } from 'next-intl'
import { cn } from '@/lib/cn'
import { GROUP_TEXT } from './labels'
import { GroupIcon } from './Outcome'
import { GROUPS, type CheckCounts, type FindingGroup } from './types'

/** The id of the section of a group on the page of a check. */
export function groupAnchor(group: FindingGroup): string {
  return `gruppo-${group}`
}

/**
 * The four groups with their counts, in the order of what to do first. A
 * group that has findings leads to its section; an empty one is just a zero.
 */
export function GroupSummary({ counts }: { counts: CheckCounts }) {
  const t = useTranslations('controlla')
  return (
    <nav aria-label={t('detail.summaryLabel')}>
      <ul className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-rule bg-rule sm:grid-cols-4">
        {GROUPS.map((group) => {
          const count = counts[group]
          const body = (
            <>
              <span className={cn('font-serif text-h2 font-medium tabular', count > 0 ? GROUP_TEXT[group] : 'text-ink-3')}>{count}</span>
              <span className="flex items-center gap-1.5 text-small text-ink-2">
                <GroupIcon group={group} className={cn('h-3.5 w-3.5', count === 0 && 'text-ink-3')} />
                {t(`groups.${group}.label`)}
              </span>
            </>
          )
          return (
            <li key={group} className="bg-surface">
              {count > 0 ? (
                <a href={`#${groupAnchor(group)}`} className="flex h-full flex-col gap-1 px-4 py-3 no-underline hover:bg-surface-2">
                  {body}
                </a>
              ) : (
                <div className="flex h-full flex-col gap-1 px-4 py-3">{body}</div>
              )}
            </li>
          )
        })}
      </ul>
    </nav>
  )
}
