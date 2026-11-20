'use client'

import { Fragment, useMemo } from 'react'
import { useTranslations } from 'next-intl'
import { cn } from '@/lib/cn'
import { useTextContext } from '@/i18n/useTextContext'
import { parseAnswer, resolverFor, type InlineToken } from '@/lib/chiedi/answer-text'
import { markerLabel } from '@/lib/chiedi/sources'
import type { ChiediCitation } from '@/lib/chiedi/types'

/**
 * The answer text as paragraphs and lists, with every bracketed reference
 * that matches one of the answer's sources rendered as a link to it.
 */
export function AnswerBody({
  text,
  citations,
  messageId,
  activeIndex,
  onMarkerClick,
}: {
  text: string
  citations: ChiediCitation[]
  messageId: string
  activeIndex?: number | null
  onMarkerClick?: (index: number) => void
}) {
  const t = useTranslations('chiedi.answer')
  const ctx = useTextContext()
  const blocks = useMemo(() => parseAnswer(text, resolverFor(citations)), [text, citations])

  const renderInline = (tokens: InlineToken[], keyPrefix: string) =>
    tokens.map((tok, i) => {
      const key = `${keyPrefix}-${i}`
      if (tok.type === 'text') return <Fragment key={key}>{tok.text}</Fragment>
      if (tok.type === 'strong')
        return (
          <strong key={key} className="font-semibold text-ink">
            {tok.text}
          </strong>
        )
      // An act cited by its CELEX is shown by its name: "[Regolamento (UE) 2026/1744, Art. 1]".
      const shown = markerLabel(tok.label, ctx.t)
      if (tok.index === null || !onMarkerClick) return <Fragment key={key}>[{shown}]</Fragment>
      const index = tok.index
      const active = activeIndex === index
      return (
        <button
          key={key}
          type="button"
          data-marker={`${messageId}-${index}`}
          onClick={() => onMarkerClick(index)}
          aria-label={t('goToSource', { index })}
          title={t('source', { index })}
          className={cn(
            'rounded-sm px-0.5 font-medium text-union underline-offset-4 hover:underline',
            active && 'bg-union/10 underline',
          )}
        >
          [{shown}]
        </button>
      )
    })

  return (
    <div className="space-y-3 text-read text-ink">
      {blocks.map((block, bi) => {
        if (block.type === 'paragraph') return <p key={bi}>{renderInline(block.inline, `p${bi}`)}</p>
        const Tag = block.ordered ? 'ol' : 'ul'
        return (
          <Tag key={bi} className={cn('space-y-1.5 pl-6', block.ordered ? 'list-decimal' : 'list-disc')}>
            {block.items.map((item, ii) => (
              <li key={ii} className="pl-1">
                {renderInline(item, `l${bi}-${ii}`)}
              </li>
            ))}
          </Tag>
        )
      })}
    </div>
  )
}
