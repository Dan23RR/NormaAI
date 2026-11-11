'use client'

import Link from 'next/link'
import type { ReactNode } from 'react'
import { useLocale, useTranslations } from 'next-intl'
import { AlertTriangle, CheckCircle2, CircleSlash, CircleX, ExternalLink } from 'lucide-react'
import { ButtonLink } from '@/components/ui/Button'
import { Skeleton } from '@/components/ui/Skeleton'
import { useDateFormat } from '@/i18n/useDateFormat'
import { useTextContext } from '@/i18n/useTextContext'
import { cn } from '@/lib/cn'
import { dependencyUrl, originName, versionLabel } from './labels'
import { isStale, type Dependency, type DependencyState, type DocumentCheck } from './types'

/** The client a check is tied to, as far as the page could tell. */
export type ClientLink = { state: 'none' } | { state: 'loading' } | { state: 'gone' } | { state: 'found'; id: string; name: string }

const STATE_ICON = {
  current: CheckCircle2,
  changed: AlertTriangle,
  removed: CircleX,
  unavailable: CircleSlash,
} as const

const STATE_TEXT: Record<DependencyState, string> = {
  current: 'text-ok',
  changed: 'text-warn',
  removed: 'text-bad',
  unavailable: 'text-ink-2',
}

/** What the last re-check found for a provision: an icon and the words, never the colour alone. */
function StateMark({ state }: { state: DependencyState }) {
  const t = useTranslations('controlla.dependencies.state')
  const Icon = STATE_ICON[state]
  return (
    <span className={cn('inline-flex items-center gap-1', STATE_TEXT[state])}>
      <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      {t(state)}
    </span>
  )
}

function OfficialLink({ dependency }: { dependency: Dependency }) {
  const locale = useLocale()
  const url = dependencyUrl(dependency, locale)
  const origin = originName(url, dependency.source)
  if (!url || !origin) return null
  return (
    <a href={url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-union hover:underline">
      {origin}
      <ExternalLink className="h-3 w-3" aria-hidden="true" />
    </a>
  )
}

function Fact({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-caption text-ink-2">{term}</dt>
      <dd className="text-small text-ink">{children}</dd>
    </div>
  )
}

/** What is kept of the document: the dated facts, and the reminder that the file is not among them. */
export function CheckFacts({ check, client }: { check: DocumentCheck; client: ClientLink }) {
  const t = useTranslations('controlla.facts')
  const formatDate = useDateFormat()
  const language = check.lang === 'IT' || check.lang === 'EN' ? t(`languages.${check.lang}`) : check.lang
  return (
    <section aria-labelledby="check-facts-heading">
      <h2 id="check-facts-heading" className="text-h4">
        {t('title')}
      </h2>
      <dl className="mt-3 space-y-2.5">
        <Fact term={t('checked')}>{check.checked_at ? formatDate(check.checked_at) : t('noDate')}</Fact>
        <Fact term={t('documentDate')}>{check.document_date ? formatDate(check.document_date) : t('noDate')}</Fact>
        <Fact term={t('client')}>
          {client.state === 'found' ? (
            <Link href={`/app/clienti/${encodeURIComponent(client.id)}`} className="text-union hover:underline">
              {client.name}
            </Link>
          ) : client.state === 'gone' ? (
            t('clientGone')
          ) : client.state === 'loading' ? (
            <Skeleton className="mt-0.5 h-4 w-32" />
          ) : (
            t('noClient')
          )}
        </Fact>
        <Fact term={t('language')}>{language}</Fact>
        <Fact term={t('watch')}>{check.watch ? t('watchOn') : t('watchOff')}</Fact>
        {check.document_sha256 && (
          <Fact term={t('sha')}>
            <span className="break-all font-mono text-caption text-ink-2">{check.document_sha256}</span>
          </Fact>
        )}
      </dl>
      <p className="mt-3 text-caption text-ink-2">{t('notStored')}</p>
    </section>
  )
}

/** The provisions the document depends on, each with the version it was checked against and its state. */
export function DependenciesList({ check }: { check: DocumentCheck }) {
  const t = useTranslations('controlla.dependencies')
  const ctx = useTextContext()
  const formatDate = useDateFormat()
  const dependencies = check.dependencies
  return (
    <section aria-labelledby="check-dependencies-heading">
      <h2 id="check-dependencies-heading" className="text-h4">
        {t('title', { count: dependencies.length })}
      </h2>
      {dependencies.length === 0 ? (
        <p className="mt-1 text-small text-ink-2">{t('none')}</p>
      ) : (
        <>
          <p className="mt-1 text-small text-ink-2">{check.watch ? t('watched') : t('notWatched')}</p>
          <ul className="mt-2 divide-y divide-rule">
            {dependencies.map((dependency) => (
              <li key={`${dependency.act}-${dependency.key}`} className="py-2.5">
                <p className="break-words text-small font-medium text-ink">
                  {dependency.name}, {dependency.article}
                </p>
                <p className="text-caption text-ink-2">{t('checkedOn', { version: versionLabel(dependency.as_of, ctx) })}</p>
                <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-caption">
                  <StateMark state={dependency.state} />
                  {isStale(dependency) && dependency.changed_at && (
                    <span className="text-ink-2">{t('detectedOn', { date: formatDate(dependency.changed_at) })}</span>
                  )}
                  <OfficialLink dependency={dependency} />
                </p>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}

/**
 * Shown when a re-check found that a cited provision changed after the
 * document was checked: which ones, when it was found, and what to do.
 */
export function ReviewNotice({ check }: { check: DocumentCheck }) {
  const t = useTranslations('controlla.review')
  const td = useTranslations('controlla.dependencies')
  const formatDate = useDateFormat()
  const changed = check.dependencies.filter(isStale)
  const date = check.checked_at ? formatDate(check.checked_at) : ''
  const again = check.client_id ? `/app/controlla?cliente=${encodeURIComponent(check.client_id)}` : '/app/controlla'
  return (
    <section aria-labelledby="check-review-heading" className="rounded-lg border border-warn/40 bg-warn/5 px-5 py-4">
      <h2 id="check-review-heading" className="flex items-center gap-2 text-h4">
        <AlertTriangle className="h-4 w-4 shrink-0 text-warn" aria-hidden="true" />
        {t('title')}
      </h2>
      <p className="mt-1 text-body text-ink">{changed.length > 0 ? t('body', { date, count: changed.length }) : t('bodyUnknown', { date })}</p>
      {changed.length > 0 && (
        <ul className="mt-2 space-y-1.5">
          {changed.map((dependency) => (
            <li key={`${dependency.act}-${dependency.key}`} className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-small">
              <span className="font-medium text-ink">
                {dependency.name}, {dependency.article}
              </span>
              <StateMark state={dependency.state} />
              {dependency.changed_at && <span className="text-ink-2">{td('detectedOn', { date: formatDate(dependency.changed_at) })}</span>}
              <OfficialLink dependency={dependency} />
            </li>
          ))}
        </ul>
      )}
      <p className="mt-3 text-small text-ink-2">{t('whatToDo')}</p>
      <ButtonLink href={again} variant="secondary" size="sm" className="mt-3">
        {t('newCheck')}
      </ButtonLink>
    </section>
  )
}
