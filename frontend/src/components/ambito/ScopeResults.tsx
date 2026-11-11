'use client'

import { useTranslations } from 'next-intl'
import { CalendarClock, Copy, Link2 } from 'lucide-react'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { useTextContext } from '@/i18n/useTextContext'
import { STATUS_TONE, byRelevance, frameworkBadge, frameworkTitle, inputSummary, statusLabel } from '@/lib/scope/text'
import type { ScopeAssessment, ScopeResult } from '@/lib/scope/types'
import { FrameworkTag, SourceEntry } from './SourceCitation'

/** Up to this many sources the legal basis is open; a longer one opens on request. */
const OPEN_SOURCES = 6

function LegalBasis({ result }: { result: ScopeResult }) {
  const t = useTranslations('ambito.results')
  const verified = result.sources.filter((s) => s.status === 'verified').length
  return (
    <details className="group border-t border-rule pt-4" open={result.sources.length <= OPEN_SOURCES}>
      <summary className="cursor-pointer rounded-sm font-sans text-small text-ink-2 marker:text-ink-3">
        <span className="font-medium">{t('legalBasis')}</span>
        <span className="ml-2 text-ink-3">{t('legalBasisSummary', { count: result.sources.length, verified })}</span>
      </summary>
      <ul className="mt-3 space-y-3">
        {result.sources.map((s) => (
          <SourceEntry key={s.id} source={s} />
        ))}
      </ul>
    </details>
  )
}

function ResultBlock({ result }: { result: ScopeResult }) {
  const t = useTranslations('ambito.results')
  const ctx = useTextContext()
  const muted = result.status === 'not_assessed'
  return (
    <section aria-labelledby={`scope-result-${result.framework}`} className="rounded-lg border border-rule bg-surface">
      <div className="flex flex-wrap items-center gap-2 border-b border-rule px-5 py-3">
        <FrameworkTag framework={result.framework} label={frameworkBadge(result.framework, ctx.t)} />
        <h2 id={`scope-result-${result.framework}`} className="font-sans text-body font-medium text-ink">
          {frameworkTitle(result.framework, ctx.t)}
        </h2>
        <Badge tone={STATUS_TONE[result.status]} className="ml-auto">
          {statusLabel(result.status, ctx.t)}
        </Badge>
      </div>

      <div className="space-y-4 px-5 py-5">
        <p className={muted ? 'text-body text-ink-2' : 'font-serif text-h4 text-ink'}>{result.headline}</p>

        {result.fromLabel && (
          <p className="flex items-start gap-2 text-small text-ink-2">
            <CalendarClock className="mt-0.5 h-4 w-4 shrink-0 text-ink-3" aria-hidden="true" />
            {result.fromLabel}
          </p>
        )}

        {result.reasons.length > 0 && (
          <ul className="list-disc space-y-1.5 pl-5 text-body text-ink">
            {result.reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        )}

        {result.obligations && result.obligations.length > 0 && (
          <div>
            <h3 className="font-sans text-small font-medium text-ink-2">{t('duties')}</h3>
            <div className="mt-2 space-y-3">
              {result.obligations.map((o) => (
                <article key={o.key} className="rounded-md border border-rule bg-surface-2 px-4 py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={o.who === 'deployer' ? 'neutral' : 'union'}>{o.whoLabel}</Badge>
                    <span className="text-small tabular text-ink-3">{o.article}</span>
                  </div>
                  <h4 className="mt-2 font-sans text-body font-medium text-ink">{o.title}</h4>
                  <p className="mt-1 text-small text-ink">{o.requirement}</p>
                  {o.exception && <p className="mt-1.5 text-small text-ink-2">{o.exception}</p>}
                </article>
              ))}
            </div>
          </div>
        )}

        {result.notes.length > 0 && (
          <div>
            <h3 className="font-sans text-small font-medium text-ink-2">{t('notes')}</h3>
            <ul className="mt-1.5 list-disc space-y-1 pl-5 text-small text-ink-2">
              {result.notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </div>
        )}

        <LegalBasis result={result} />
        <p className="text-caption text-ink-3">{t('filterNote')}</p>
      </div>
    </section>
  )
}

export function ScopeResults({
  assessment,
  onCopyResult,
  onCopyLink,
}: {
  assessment: ScopeAssessment
  onCopyResult: () => void
  onCopyLink: () => void
}) {
  const t = useTranslations('ambito.results')
  const ctx = useTextContext()
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-h3">{t('title')}</h2>
          <p className="mt-1 text-small text-ink-2">{inputSummary(assessment.input, ctx)}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="secondary" size="sm" iconLeft={<Copy className="h-4 w-4" aria-hidden="true" />} onClick={onCopyResult}>
            {t('copyResult')}
          </Button>
          <Button type="button" variant="ghost" size="sm" iconLeft={<Link2 className="h-4 w-4" aria-hidden="true" />} onClick={onCopyLink}>
            {t('copyLink')}
          </Button>
        </div>
      </div>
      {byRelevance(assessment.results).map((r) => (
        <ResultBlock key={r.framework} result={r} />
      ))}
    </div>
  )
}
