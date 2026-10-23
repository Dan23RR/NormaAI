'use client'

import { useMemo } from 'react'
import { useTranslations } from 'next-intl'
import { AlertTriangle, ChevronDown, Copy } from 'lucide-react'
import { Button, Spinner } from '@/components/ui/Button'
import { FrameworkBadge, frameworkLabel } from '@/components/ui/Badge'
import { cn } from '@/lib/cn'
import { useTextContext } from '@/i18n/useTextContext'
import { getConfidenceLabel } from '@/lib/confidence-labels'
import { detectAbstention } from '@/lib/chiedi/abstention'
import { buildCopyText } from '@/lib/chiedi/copy'
import { phaseLabel } from '@/lib/chiedi/phases'
import { citationsToSources, normalizeFramework } from '@/lib/chiedi/sources'
import { citationsOf, type AssistantMessage } from '@/lib/chiedi/types'
import { AbstentionNotice } from './AbstentionNotice'
import { AiNotice } from './AiNotice'
import { AnswerBody } from './AnswerBody'
import { SourcesList } from './SourcesList'

function StatusLine({ label }: { label: string }) {
  return (
    <p className="flex items-center gap-2 text-small text-ink-2">
      <Spinner className="h-3.5 w-3.5 text-union" />
      {label}
    </p>
  )
}

/** One answer of the conversation, in every state it can be in. */
export function AnswerTurn({
  message,
  demo,
  activeIndex,
  sourcesOpen,
  onToggleSources,
  onMarkerClick,
  onSourceSelect,
  onFollowUp,
  onRetry,
  onCopy,
}: {
  message: AssistantMessage
  demo: boolean
  activeIndex: number | null
  sourcesOpen: boolean
  onToggleSources: () => void
  onMarkerClick: (index: number) => void
  onSourceSelect: (index: number) => void
  onFollowUp: (question: string) => void
  onRetry: () => void
  onCopy: (text: string) => void
}) {
  const t = useTranslations('chiedi')
  const ctx = useTextContext()
  const citations = useMemo(() => citationsOf(message), [message])
  const sources = useMemo(() => citationsToSources(citations, message.id, ctx), [citations, message.id, ctx])
  const mobileSources = useMemo(() => citationsToSources(citations, `m-${message.id}`, ctx), [citations, message.id, ctx])
  const data = message.data
  const abstention = useMemo(() => detectAbstention(data), [data])

  const label = <p className="text-small text-ink-3">{t('answerLabel')}</p>

  if (message.status === 'error') {
    return (
      <div>
        {label}
        <div role="alert" className="mt-2 rounded-lg border border-bad/30 bg-bad/5 px-4 py-3">
          <p className="text-body text-ink">{message.error ?? t('errors.failed')}</p>
          <Button variant="secondary" size="sm" className="mt-3" onClick={onRetry}>
            {t('answer.retry')}
          </Button>
        </div>
      </div>
    )
  }

  if (message.status === 'loading' || message.status === 'streaming') {
    return (
      <div>
        {label}
        {message.content && (
          <div className="mt-2">
            <AnswerBody text={message.content} citations={citations} messageId={message.id} activeIndex={activeIndex} onMarkerClick={onMarkerClick} />
          </div>
        )}
        <div className={cn(message.content ? 'mt-3' : 'mt-2')}>
          <StatusLine label={message.status === 'loading' ? phaseLabel(undefined, ctx.t) : phaseLabel(message.phase ?? 'draft', ctx.t)} />
        </div>
      </div>
    )
  }

  if (!data) return null

  if (abstention.abstained) {
    return (
      <div>
        {label}
        <div className="mt-2">
          <AbstentionNotice
            code={abstention.code}
            reason={abstention.reason}
            suggestions={data.suggested_questions}
            onSuggestion={onFollowUp}
            corpusAsOf={message.corpusAsOf}
            demo={demo}
          />
        </div>
      </div>
    )
  }

  const confidence = getConfidenceLabel(data.confidence_score ?? 0, ctx.t)
  const caveats = [...(data.caveats ?? [])]
  if (data.grounding_warning) caveats.push(t('answer.groundingCaveat'))
  const related = Array.from(new Set((data.related_frameworks ?? []).map(normalizeFramework).filter(Boolean)))

  const copy = () =>
    onCopy(buildCopyText({ answer: message.content, sources, corpusAsOf: message.corpusAsOf, demo }, ctx))

  return (
    <div>
      {label}
      <div className="mt-2">
        <AnswerBody text={message.content} citations={citations} messageId={message.id} activeIndex={activeIndex} onMarkerClick={onMarkerClick} />
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2">
        <span
          className={cn('inline-flex items-center rounded-sm border px-2 py-0.5 text-caption font-medium', confidence.color, confidence.bg, confidence.border)}
          title={confidence.sublabel}
        >
          {confidence.label}
        </span>
        {data.requires_expert_review && (
          <span className="inline-flex items-center gap-1.5 text-small text-warn">
            <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
            {t('answer.expertReview')}
          </span>
        )}
        {data.cove_applied === true && <span className="text-caption text-ink-3">{t('answer.coveApplied')}</span>}
      </div>

      {caveats.length > 0 && (
        <ul className="mt-3 space-y-1.5 border-l-2 border-warn/50 pl-3" aria-label={t('answer.caveats')}>
          {caveats.map((c, i) => (
            <li key={i} className="text-small text-ink-2">
              {c}
            </li>
          ))}
        </ul>
      )}

      {related.length > 0 && (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="text-small text-ink-2">{t('answer.related')}</span>
          {related.map((fw) => {
            const framework = frameworkLabel(fw, ctx.t)
            return (
              <button
                key={fw}
                type="button"
                onClick={() => onFollowUp(t('answer.followUp', { framework }))}
                aria-label={t('answer.askAbout', { framework })}
                className="rounded-sm hover:opacity-80"
              >
                <FrameworkBadge framework={fw} />
              </button>
            )
          })}
        </div>
      )}

      <div className="mt-4 lg:hidden">
        <button
          type="button"
          onClick={onToggleSources}
          aria-expanded={sourcesOpen}
          aria-controls={`sources-${message.id}`}
          className="inline-flex items-center gap-1.5 text-small font-medium text-ink"
        >
          <ChevronDown className={cn('h-4 w-4 text-ink-3 transition-transform', sourcesOpen && 'rotate-180')} aria-hidden="true" />
          {t('answer.sourcesToggle', { count: mobileSources.length })}
        </button>
        {sourcesOpen && (
          <div id={`sources-${message.id}`} className="mt-2 rounded-lg border border-rule bg-surface p-2">
            <SourcesList sources={mobileSources} activeIndex={activeIndex} onSelect={onSourceSelect} label={t('answer.sourcesOfAnswer')} />
          </div>
        )}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button variant="secondary" size="sm" iconLeft={<Copy className="h-3.5 w-3.5" aria-hidden="true" />} onClick={copy}>
          {t('answer.copy')}
        </Button>
      </div>

      <AiNotice corpusAsOf={message.corpusAsOf} demo={demo} className="mt-3" />
    </div>
  )
}
