'use client'

import { useMemo, type ReactNode } from 'react'
import { useTranslations } from 'next-intl'
import { AlertTriangle, ChevronDown, ExternalLink } from 'lucide-react'
import { LawQuote } from '@/components/ui/LawQuote'
import { useDateFormat } from '@/i18n/useDateFormat'
import { useTextContext } from '@/i18n/useTextContext'
import { changedSpan, diffRuns, looseKey, splitWords, type ChangedSpan } from '@/lib/word-diff'
import { actTitle, localizeVersionLabel, originName, safeUrl, versionLabel } from './labels'
import { OutcomeBadge } from './Outcome'
import { isStale, type Dependency, type Difference, type Finding } from './types'
import { WordDiff } from './WordDiff'

/** What a finding needs to know about the check it belongs to. */
export interface FindingSetting {
  /** When the document was checked (ISO): the day the official text was read. */
  checkedAt: string
  /** Language of the document, and so of the law it quotes: "IT" or "EN". */
  lang: string
}

interface FindingProps extends FindingSetting {
  finding: Finding
  /** The provision the finding rests on, with what the last re-check found. */
  dependency?: Dependency
}

/** "GDPR, art. 33, par. 1": the short name of the act and the provision, as a consultant says it. */
export function findingTitle(finding: Finding, noAct: string): string {
  const act = finding.act?.name || finding.act?.label || noAct
  const provision = finding.provision?.label || finding.raw
  return provision ? `${act}, ${provision}` : act
}

/** The quote of the document that the official wording almost matched: the one sharing most words with it. */
function closestQuote(quotes: string[], official: string): string | undefined {
  const officialWords = splitWords(official)
  let best: string | undefined
  let bestShared = -1
  for (const quote of quotes) {
    const shared = diffRuns(splitWords(quote), officialWords, looseKey)
      .filter((run) => run.kind === 'equal')
      .reduce((sum, run) => sum + (run.a2 - run.a1), 0)
    if (shared > bestShared) {
      best = quote
      bestShared = shared
    }
  }
  return best
}

function Label({ children }: { children: ReactNode }) {
  return <p className="text-small text-ink-2">{children}</p>
}

/** The reference inside its line of the document, set apart by weight (the highlighter is for the law only). */
function ContextLine({ context, raw }: { context: string; raw: string }) {
  const at = raw ? context.indexOf(raw) : -1
  if (at < 0) return <>{context}</>
  return (
    <>
      {context.slice(0, at)}
      <strong className="font-semibold text-ink">{raw}</strong>
      {context.slice(at + raw.length)}
    </>
  )
}

function DifferenceLine({ difference }: { difference: Difference }) {
  const t = useTranslations('controlla.finding')
  const key = difference.quoted && difference.official ? 'differenceBoth' : difference.official ? 'differenceMissing' : 'differenceExtra'
  return (
    <li>
      {t.rich(key, {
        quoted: difference.quoted,
        official: difference.official,
        w: (chunks) => <span className="font-semibold tabular">{chunks}</span>,
      })}
    </li>
  )
}

/**
 * Everything the check says about one reference: where it is in the
 * document, the outcome in sentences, the words that differ, the official
 * wording under the highlighter, the provision before and after a change,
 * and the way to the official text.
 */
export function FindingBody({ finding, dependency, checkedAt, lang }: FindingProps) {
  const t = useTranslations('controlla.finding')
  const ctx = useTextContext()
  const formatDate = useDateFormat()
  const stale = isStale(dependency)
  const official = finding.official_quote
  const url = safeUrl(finding.url)
  const origin = originName(url, finding.act?.source)
  const quoteLang = lang.toLowerCase()

  // An altered quote: the highlighter goes on the official words the document changed.
  const span = useMemo<ChangedSpan | null>(() => {
    if (!official || finding.differences.length === 0) return null
    const quote = closestQuote(finding.quotes, official)
    return quote ? changedSpan(quote, official) : null
  }, [official, finding.differences, finding.quotes])

  // A quote found in another article keeps the act but not the article the document names.
  const elsewhere = finding.status.code === 'altro_articolo'
  const celex = finding.act?.source === 'eurlex' ? finding.act.id : undefined

  return (
    <div className="space-y-4">
      {stale && dependency && (
        <p className="flex items-start gap-2 rounded-md border border-warn/40 bg-warn/5 px-3 py-2 text-small text-ink">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warn" aria-hidden="true" />
          <span>
            {t(dependency.state === 'removed' ? 'staleRemoved' : 'stale', { version: versionLabel(dependency.as_of, ctx) })}
          </span>
        </p>
      )}

      <div>
        <Label>{finding.line > 0 ? t('inDocument', { line: finding.line }) : t('inDocumentNoLine')}</Label>
        {finding.context && (
          <p className="mt-1 break-words text-body text-ink-2">
            <ContextLine context={finding.context} raw={finding.raw} />
          </p>
        )}
        {finding.quotes.length > 0 && (
          <div className="mt-2 space-y-2">
            {finding.quotes.map((quote, index) => (
              <figure key={index} className="border-l-2 border-rule-2 pl-3">
                <figcaption className="text-caption text-ink-2">{t('quote')}</figcaption>
                <blockquote className="break-words text-body text-ink" lang={quoteLang}>
                  {t('quoted', { text: quote })}
                </blockquote>
              </figure>
            ))}
          </div>
        )}
      </div>

      {finding.messages.length > 0 && (
        <div>
          <Label>{t('outcome')}</Label>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-body text-ink">
            {finding.messages.map((message, index) => (
              <li key={index}>{message}</li>
            ))}
          </ul>
        </div>
      )}

      {finding.differences.length > 0 && (
        <div>
          <Label>{t('differences')}</Label>
          <ul className="mt-1 space-y-1 text-body text-ink">
            {finding.differences.map((difference, index) => (
              <DifferenceLine key={index} difference={difference} />
            ))}
          </ul>
        </div>
      )}

      {official && (
        <div>
          <Label>{t('official')}</Label>
          <LawQuote
            className="mt-2"
            quote={span ? span.changed : official}
            before={span?.before || undefined}
            after={span?.after || undefined}
            act={actTitle(finding.act, ctx.t)}
            article={elsewhere ? undefined : finding.provision?.label}
            celex={celex}
            url={url}
            origin={origin}
            // The passage shown is the official text as read on the day of the check;
            // once a re-check found the provision changed, it is to be verified again.
            status={stale ? 'unverified' : 'verified'}
            verifiedAt={stale ? undefined : formatDate(checkedAt)}
            lang={quoteLang}
          />
        </div>
      )}

      {finding.before && finding.after_text && (
        <div>
          <Label>{t('change')}</Label>
          <p className="mt-1 text-small text-ink-2">
            {t('changeFromTo', {
              before: localizeVersionLabel(finding.before.version_label, ctx),
              after: finding.version ? versionLabel(finding.version.as_of, ctx) : localizeVersionLabel(null, ctx),
            })}
          </p>
          <WordDiff className="mt-2" before={finding.before.text} after={finding.after_text} lang={quoteLang} />
        </div>
      )}

      {finding.before && !finding.after_text && (
        <div>
          <Label>{t('former', { version: localizeVersionLabel(finding.before.version_label, ctx) })}</Label>
          <blockquote
            className="mt-2 max-h-64 overflow-y-auto whitespace-pre-line break-words border-l-2 border-rule-2 pl-3 font-serif text-read leading-relaxed text-ink"
            lang={quoteLang}
            tabIndex={0}
          >
            {finding.before.text}
          </blockquote>
        </div>
      )}

      {!official && url && (
        <p>
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-small font-medium text-union hover:underline"
          >
            {origin ? t(finding.group === 'non_coperto' ? 'openSource' : 'openOfficial', { origin }) : t('openGeneric')}
            <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
          </a>
        </p>
      )}
    </div>
  )
}

function Compared({ finding }: { finding: Finding }) {
  const t = useTranslations('controlla.finding')
  const ctx = useTextContext()
  if (!finding.version) return null
  return <p className="mt-0.5 text-small text-ink-2">{t('comparedWith', { version: versionLabel(finding.version.as_of, ctx) })}</p>
}

/** A finding that asks for attention: shown in full. */
export function FindingCard(props: FindingProps) {
  const t = useTranslations('controlla.finding')
  const { finding } = props
  const headingId = `finding-${finding.id}`
  return (
    <article aria-labelledby={headingId}>
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <h3 id={headingId} className="min-w-0 break-words text-h4">
          {findingTitle(finding, t('noAct'))}
        </h3>
        <OutcomeBadge group={finding.group} status={finding.status} />
      </div>
      <Compared finding={finding} />
      <div className="mt-3">
        <FindingBody {...props} />
      </div>
    </article>
  )
}

/** A finding that is fine or outside the texts: one line, the details on request. */
export function FindingRow(props: FindingProps) {
  const t = useTranslations('controlla.finding')
  const { finding } = props
  return (
    <details className="group">
      <summary className="flex cursor-pointer list-none flex-wrap items-start gap-x-3 gap-y-1.5 rounded-md py-1 [&::-webkit-details-marker]:hidden">
        <ChevronDown className="mt-1 h-4 w-4 shrink-0 text-ink-3 transition-transform group-open:rotate-180" aria-hidden="true" />
        <span className="min-w-0 flex-1 basis-48">
          <span className="block break-words font-medium text-ink">{findingTitle(finding, t('noAct'))}</span>
          {finding.line > 0 && <span className="block text-small text-ink-2">{t('line', { line: finding.line })}</span>}
        </span>
        <OutcomeBadge group={finding.group} status={finding.status} />
      </summary>
      <div className="mt-3 pb-2 pl-7">
        <FindingBody {...props} />
      </div>
    </details>
  )
}
