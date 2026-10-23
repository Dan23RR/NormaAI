import type { ChiediResponse } from './types'

export interface AbstentionInfo {
  abstained: boolean
  /** Machine code: the backend's `abstention_reason`, or how it was inferred. */
  code?: string
  /** The explanation the backend wrote, when the answer text itself is the reason. */
  reason?: string
}

/** The codes with a sentence of their own in the `chiedi.abstention.reasons` messages. */
export const ABSTENTION_CODES = ['snc_low_trust', 'no_evidence', 'demo_not_covered'] as const

/**
 * How the backend says "I will not answer this":
 * - the SNC trust layer returns `abstention_reason: "snc_low_trust"` with no
 *   citations (src/agents/snc_node.py, abstain_response_node);
 * - the Q&A prompt (prompts/qa_bot.txt) makes the model reply with a fixed
 *   sentence when the retrieved text does not cover the question, again
 *   with no citations.
 * In the stream only the text arrives, so the wording is checked too.
 */
const ABSTENTION_WORDING = [
  /non posso fornire una risposta/i,
  /non ho (?:abbastanza )?informazioni sufficienti/i,
  /non dispongo di informazioni sufficienti/i,
  /non sono in grado di rispondere/i,
  /non (?:è|e') possibile rispondere/i,
  /i (?:don'?t|do not) have (?:enough|sufficient) information/i,
  /insufficient information in my regulatory database/i,
  /(?:unable|not able) to answer/i,
  /cannot answer this question/i,
]

export function detectAbstention(
  res: Pick<ChiediResponse, 'answer' | 'citations' | 'abstention_reason'> | null | undefined,
): AbstentionInfo {
  if (!res) return { abstained: false }
  const answer = (res.answer ?? '').trim()
  const noCitations = !res.citations || res.citations.length === 0

  if (typeof res.abstention_reason === 'string' && res.abstention_reason.trim()) {
    const code = res.abstention_reason.trim()
    return { abstained: true, code, reason: answer || undefined }
  }

  if (noCitations && answer && ABSTENTION_WORDING.some((re) => re.test(answer))) {
    return { abstained: true, code: 'no_evidence', reason: answer }
  }

  return { abstained: false }
}
