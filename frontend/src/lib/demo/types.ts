import type { QAResponse } from '../types'

/**
 * A citation of a demo answer: the base contract of POST /api/v1/qa plus the
 * optional fields the SSE citation events carry (verified, celex, url,
 * article). `verified: true` is used only for a passage that
 * scripts/check_demo_quotes.py finds word for word in the official text.
 */
export type DemoCitation = QAResponse['citations'][number] & {
  verified?: boolean
  celex?: string
  url?: string
  article?: string
  title?: string
  /** Date of the consolidated text the passage was read in (see acts.ts). */
  consolidated_as_of?: string
}

export type DemoQAResponse = Omit<QAResponse, 'citations'> & {
  citations: DemoCitation[]
  abstention_reason?: string
  suggested_questions?: string[]
  /** Example corpus date of the demo (the real one travels in the response metadata). */
  corpus_as_of?: string
}

/** The answers of the demo, by scenario. Both languages must define the same scenarios. */
export type DemoQAScenario =
  | 'csrd'
  | 'csddd'
  | 'value_chain'
  | 'ai_act'
  | 'ai_act_art50'
  | 'ai_act_art4'
  | 'ai_act_art9'
  | 'gdpr'
  | 'gdpr_art9'
  | 'gdpr_art13'
  | 'gdpr_art17'
  | 'gdpr_dpo'
  | 'dora'
  | 'dora_art30'
  | 'nis2'
  | 'taxonomy'
  | 'cross_ai_gdpr'
  | 'cross_dora_nis2'

/** The part of a company profile the demo scenarios look at. */
export interface DemoProfile {
  name?: string
  sector?: string
  employee_count?: number
  revenue_eur?: number
}
