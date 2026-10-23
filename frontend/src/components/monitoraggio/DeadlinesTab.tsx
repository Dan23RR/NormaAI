'use client'

import { useMemo } from 'react'
import { useLocale, useTranslations } from 'next-intl'
import { ExternalLink } from 'lucide-react'
import { Badge, FrameworkBadge } from '@/components/ui/Badge'
import { EmptyState } from '@/components/ui/EmptyState'
import { formatMonthHeading } from '@/i18n/format'
import { useDateFormat } from '@/i18n/useDateFormat'
import { useTextContext } from '@/i18n/useTextContext'
import { groupByMonth, obligations, past, upcoming, type Obligation } from '@/lib/obligations/calendar'
import { addDays, toIsoDate } from '@/lib/obligations/dates'

function ObligationRow({ o, compact }: { o: Obligation; compact?: boolean }) {
  const t = useTranslations('monitoraggio.deadlines')
  const tu = useTranslations('ui')
  const formatDate = useDateFormat()
  return (
    <li className="grid gap-x-6 gap-y-1.5 py-4 sm:grid-cols-[11rem_minmax(0,1fr)]">
      <div className="flex flex-wrap items-center gap-2 sm:flex-col sm:items-start">
        <time dateTime={o.date} className="text-body font-medium tabular text-ink">
          {formatDate(o.date, o.precision)}
        </time>
        <FrameworkBadge framework={o.framework} />
        {!o.confirmed && <Badge tone="warn">{t('expected')}</Badge>}
      </div>
      <div className="min-w-0">
        <h4 className="font-sans text-body font-medium text-ink">{o.title}</h4>
        <p className="mt-0.5 text-small text-ink-2">
          <span className="text-ink-3">{t('who')}</span>
          {o.who}
        </p>
        {!compact && (
          <p className="mt-0.5 text-small text-ink-2">
            <span className="text-ink-3">{t('what')}</span>
            {o.what}
          </p>
        )}
        <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-caption text-ink-3">
          <span>
            <span className="font-medium text-ink-2">{o.source.act}</span>
            {o.source.article && <span>, {o.source.article}</span>}
          </span>
          {o.source.celex && <span className="tabular">{tu('celex', { celex: o.source.celex })}</span>}
          {o.source.url && (
            <a
              href={o.source.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-union hover:underline"
            >
              {o.source.origin ?? tu('text')}
              <ExternalLink className="h-3 w-3" aria-hidden="true" />
            </a>
          )}
          <span title={t('readIn', { note: o.sourceNote })}>{t('verifiedOn', { date: formatDate(o.verifiedOn) })}</span>
        </p>
      </div>
    </li>
  )
}

/**
 * The next twelve months of dated obligations, grouped by month, followed by
 * the milestones already in application. Nothing here is live: the list is
 * curated by hand and every row carries the date it was verified.
 */
export function DeadlinesTab({ today = new Date(), days = 365 }: { today?: Date; days?: number }) {
  const t = useTranslations('monitoraggio.deadlines')
  const locale = useLocale()
  const ctx = useTextContext()
  const formatDate = useDateFormat()
  const list = useMemo(() => obligations(ctx), [ctx])
  const groups = useMemo(() => groupByMonth(upcoming(today, days, list)), [today, days, list])
  const earlier = useMemo(() => past(today, list), [today, list])
  const from = toIsoDate(today)
  const to = toIsoDate(addDays(today, days))

  return (
    <div className="space-y-10">
      <section aria-labelledby="deadlines-upcoming">
        <h2 id="deadlines-upcoming" className="text-h3">
          {t('upcoming')}
        </h2>
        <p className="mt-1 text-small text-ink-2">{t('range', { from: formatDate(from), to: formatDate(to) })}</p>
        {groups.length === 0 ? (
          <EmptyState className="mt-6" title={t('emptyTitle')} description={t('emptyDescription')} />
        ) : (
          groups.map((g) => (
            <section key={g.key} aria-labelledby={`deadlines-month-${g.key}`} className="mt-6">
              <h3
                id={`deadlines-month-${g.key}`}
                className="border-b border-rule pb-2 font-sans text-small font-medium text-ink-2"
              >
                {formatMonthHeading(g.firstDay, locale)}
              </h3>
              <ol className="divide-y divide-rule">
                {g.items.map((o) => (
                  <ObligationRow key={o.id} o={o} />
                ))}
              </ol>
            </section>
          ))
        )}
      </section>

      {earlier.length > 0 && (
        <section aria-labelledby="deadlines-past">
          <h2 id="deadlines-past" className="text-h3">
            {t('past')}
          </h2>
          <p className="mt-1 text-small text-ink-2">{t('pastLead')}</p>
          <ol className="mt-2 divide-y divide-rule">
            {earlier.map((o) => (
              <ObligationRow key={o.id} o={o} compact />
            ))}
          </ol>
        </section>
      )}
    </div>
  )
}
