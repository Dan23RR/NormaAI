'use client'

import { ExternalLink } from 'lucide-react'
import { AiNotice } from './AiNotice'

const EURLEX_SEARCH = 'https://eur-lex.europa.eu/homepage.html?locale=it'

/**
 * Shown instead of an answer when the backend abstains: the reason, what
 * to do next, and (demo only) example questions the demo does cover.
 */
export function AbstentionNotice({
  reason,
  suggestions,
  onSuggestion,
  corpusAsOf,
  demo,
}: {
  reason?: string
  suggestions?: string[]
  onSuggestion?: (question: string) => void
  corpusAsOf?: string
  demo?: boolean
}) {
  return (
    <div className="rounded-lg border border-rule bg-surface-2 px-5 py-5">
      <h3 className="text-h4">NormaAI non risponde a questa domanda</h3>
      {reason && <p className="mt-2 text-body text-ink-2">{reason}</p>}
      <p className="mt-3 text-body text-ink">
        Cosa puoi fare: riformula la domanda indicando l&rsquo;atto, l&rsquo;articolo o il caso concreto, oppure consulta
        direttamente il testo dell&rsquo;atto su EUR-Lex.
      </p>
      <a
        href={EURLEX_SEARCH}
        target="_blank"
        rel="noopener noreferrer"
        className="mt-2 inline-flex items-center gap-1 text-small font-medium text-union hover:underline"
      >
        Apri EUR-Lex
        <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
      </a>
      {suggestions && suggestions.length > 0 && onSuggestion && (
        <div className="mt-4">
          <p className="text-small text-ink-2">Domande che la demo copre:</p>
          <ul className="mt-2 flex flex-wrap gap-2" aria-label="Domande di esempio">
            {suggestions.map((s) => (
              <li key={s}>
                <button
                  type="button"
                  onClick={() => onSuggestion(s)}
                  className="rounded-md border border-rule-2 bg-surface px-3 py-1.5 text-left text-small text-ink-2 hover:border-union hover:text-ink"
                >
                  {s}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      <AiNotice corpusAsOf={corpusAsOf} demo={demo} className="mt-4" />
    </div>
  )
}
