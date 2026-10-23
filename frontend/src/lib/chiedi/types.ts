import type { Citation, QAResponse } from '@/lib/types'

/**
 * A citation as the Chiedi page receives it: the base contract of
 * `POST /api/v1/qa` (framework, reference, quote_snippet) plus the optional
 * fields that the SSE `citation` events of `/api/v1/qa/stream` and the demo
 * data carry. `verified` is true only when the backend confirmed the passage
 * in the official text (CoVe); anything else is shown as "Da verificare".
 */
export interface ChiediCitation extends Citation {
  verified?: boolean
  celex?: string
  url?: string
  article?: string
  /** Document title as the SSE event names it (may be just a framework key). */
  title?: string
}

/** The answer payload with the fields the backend adds beyond `QAResponse`. */
export interface ChiediResponse extends Omit<QAResponse, 'citations'> {
  citations: ChiediCitation[]
  /** Set by the backend when it abstains, e.g. "snc_low_trust" (src/agents/snc_node.py). */
  abstention_reason?: string
  /** Set by the grounding guard when a citation was not found in the retrieved text. */
  grounding_warning?: string
  /** Whether the Chain-of-Verification pipeline ran (SSE `done` event). */
  cove_applied?: boolean
  /** Demo data only: example questions offered when the demo does not cover one. */
  suggested_questions?: string[]
  /** Demo data only: the example corpus date. The real one travels in the response metadata. */
  corpus_as_of?: string
}

export type Language = 'it' | 'en'

export type AssistantStatus = 'loading' | 'streaming' | 'done' | 'error'

export interface UserMessage {
  id: string
  role: 'user'
  content: string
  /** ISO timestamp. */
  timestamp: string
}

export interface AssistantMessage {
  id: string
  role: 'assistant'
  status: AssistantStatus
  /** The question this answer replies to, kept for "Riprova". */
  question: string
  language: Language
  /** The answer text, complete or being appended to by the stream. */
  content: string
  data?: ChiediResponse
  error?: string
  /** Backend phase while streaming (draft, planning, verification, revision, validation). */
  phase?: string
  /** Corpus date (ISO) from the response metadata, when the backend exposes it. */
  corpusAsOf?: string
  /** Citations received live from the stream, before the `done` event. */
  streamCitations?: ChiediCitation[]
  timestamp: string
}

export type ChatMessage = UserMessage | AssistantMessage

export function isAssistant(m: ChatMessage): m is AssistantMessage {
  return m.role === 'assistant'
}

/** The citations an answer carries, final or still arriving. */
export function citationsOf(m: AssistantMessage): ChiediCitation[] {
  return m.data?.citations ?? m.streamCitations ?? []
}
