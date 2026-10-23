'use client'

import { useTranslations } from 'next-intl'
import { CalendarClock, Copy, ExternalLink, Link2 } from 'lucide-react'
import { Badge, FrameworkBadge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { LawQuote } from '@/components/ui/LawQuote'
import { formatDate } from '@/i18n/format'
import { useTextContext } from '@/i18n/useTextContext'
import { STATUS_TONE, frameworkTitle, inputSummary, statusLabel } from '@/lib/scope/text'
import type { ScopeAssessment, ScopeResult } from '@/lib/scope/types'
import type { Source } from '@/lib/sources'

/** A compact source line: act, article, CELEX and the link to the official text. */
export function SourceLine({ source }: { source: Source }) {
  const tu = useTranslations('ui')
  return (
    <li className="text-small leading-relaxed text-ink-2">
      <span className="mr-1.5 tabular text-ink-3">[{source.index}]</span>
      <span className="font-medium text-ink">{source.act}</span>
      {source.article && <span>, {source.article}</span>}
      {source.celex && <span className="ml-2 whitespace-nowrap tabular text-ink-3">{tu('celex', { celex: source.celex })}</span>}
      {source.url && (
        <a
          href={source.url}
          target="_blank"
          rel="noopener noreferrer"
          className="ml-2 inline-flex items-center gap-1 whitespace-nowrap text-union hover:underline"
        >
          {source.origin ?? tu('text')}
          <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
        </a>
      )}
    </li>
  )
}

function ResultBlock({ result }: { result: ScopeResult }) {
  const t = useTranslations('ambito.results')
  const ctx = useTextContext()
  const muted = result.status === 'not_assessed'
  const verifiedOn = formatDate(result.verifiedOn, ctx)
  return (
    <section
      aria-labelledby={`scope-result-${result.framework}`}
      className="rounded-lg border border-rule bg-surface"
    >
      <div className="flex flex-wrap items-center gap-2 border-b border-rule px-5 py-3">
        <FrameworkBadge framework={result.framework} />
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
          <p className="inline-flex items-center gap-2 text-small text-ink-2">
            <CalendarClock className="h-4 w-4 shrink-0 text-ink-3" aria-hidden="true" />
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
          <div className="space-y-3">
            {result.obligations.map((o) => (
              <article key={o.key} className="rounded-md border border-rule bg-surface-2 px-4 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={o.who === 'provider' ? 'union' : 'neutral'}>{o.whoLabel}</Badge>
                  <span className="text-small tabular text-ink-3">{o.article}</span>
                </div>
                <h3 className="mt-2 font-sans text-body font-medium text-ink">{o.title}</h3>
                <p className="mt-1 text-small text-ink">{o.requirement}</p>
                <p className="mt-1.5 text-small text-ink-2">{o.exception}</p>
              </article>
            ))}
          </div>
        )}

        {result.passages.length > 0 && (
          <div className="space-y-4">
            {result.passages.map((p) => (
              <LawQuote
                key={p.quote}
                quote={p.quote}
                before={p.before}
                after={p.after}
                lang={p.lang}
                act={p.act}
                article={p.article}
                celex={p.celex}
                url={p.url}
                verifiedAt={verifiedOn}
                origin="EUR-Lex"
              />
            ))}
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

        <div className="border-t border-rule pt-4">
          <h3 className="font-sans text-small font-medium text-ink-2">{t('legalBasis')}</h3>
          <ul className="mt-1.5 space-y-1">
            {result.sources.map((s) => (
              <SourceLine key={s.id} source={s} />
            ))}
          </ul>
          <p className="mt-2 text-caption text-ink-3">{t('verifiedNote', { date: verifiedOn })}</p>
        </div>
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
      {assessment.results.map((r) => (
        <ResultBlock key={r.framework} result={r} />
      ))}
    </div>
  )
}
