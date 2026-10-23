'use client'

import type { ReactNode } from 'react'
import type { Source } from '@/lib/sources'
import { detectAbstention } from '@/lib/chiedi/abstention'
import type { AssistantMessage } from '@/lib/chiedi/types'
import { SourcesList } from './SourcesList'

/**
 * The margin of the annotated code: the sources of the selected answer,
 * fixed while the conversation scrolls. Desktop only; under `lg` each
 * answer carries its own collapsible sources.
 */
export function SourcesMargin({
  message,
  sources,
  activeIndex,
  totalAnswers,
  onSelect,
  children,
}: {
  message: AssistantMessage | undefined
  sources: Source[]
  activeIndex: number | null
  totalAnswers: number
  onSelect: (index: number) => void
  /** Rendered above the sources: the company profile panel. */
  children?: ReactNode
}) {
  const abstained = message?.data ? detectAbstention(message.data).abstained : false
  const waiting = message && (message.status === 'loading' || message.status === 'streaming') && sources.length === 0

  return (
    <aside aria-label="Fonti e profilo" className="hidden min-w-0 lg:block">
      <div className="sticky top-6 flex max-h-[calc(100vh-3rem)] flex-col gap-5 overflow-y-auto pr-1">
        {children}
        <section aria-labelledby="sources-heading">
          <h2 id="sources-heading" className="text-h4">
            Fonti{sources.length > 0 ? ` (${sources.length})` : ''}
          </h2>
          {message && totalAnswers > 1 && (
            <p className="mt-1 truncate text-caption text-ink-3" title={message.question}>
              Della risposta a: {message.question}
            </p>
          )}
          <div className="mt-3">
            {!message ? (
              <p className="text-small text-ink-2">
                Le fonti di ogni risposta compaiono qui: atto, articolo, passaggio citato nel testo ufficiale e stato di
                verifica.
              </p>
            ) : message.status === 'error' ? (
              <p className="text-small text-ink-2">Nessuna fonte: la risposta non è arrivata.</p>
            ) : waiting ? (
              <p className="text-small text-ink-2">Le fonti arrivano con la risposta.</p>
            ) : abstained ? (
              <p className="text-small text-ink-2">Nessuna fonte: NormaAI non ha risposto a questa domanda.</p>
            ) : (
              <SourcesList sources={sources} activeIndex={activeIndex} onSelect={onSelect} label="Fonti della risposta" />
            )}
          </div>
          {sources.length > 0 && (
            <p className="mt-4 text-caption text-ink-3">
              «Verificata»: il passaggio è stato ritrovato nel testo ufficiale. «Da verificare»: non è stato ancora
              confermato.
            </p>
          )}
        </section>
      </div>
    </aside>
  )
}
