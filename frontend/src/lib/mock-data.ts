/**
 * Demo mode ("Demo con dati di esempio"): what the API client answers when no
 * backend is involved. The demo is the office of an invented Italian firm of
 * consultants that follows a handful of small and medium-sized companies.
 *
 * The data lives in ./demo:
 *   clients.ts   the clients of the firm
 *   alerts.ts    the alerts, with fixed dates
 *   qa-it.ts     the answers of "Chiedi" in Italian, qa-en.ts in English
 *   gap.ts       the gap analyses, monitor.ts the analysis of a change
 *   acts.ts      the demo date and the version of each act that is quoted
 *
 * Two rules hold for everything in there. What is shown as a passage of law
 * is the official text, word for word (scripts/check_demo_quotes.py). And
 * nothing pretends to be live: dates are fixed and there is no server status.
 */
import type { Language } from '@/i18n/config'
import type { SystemStats, TokenPair, User } from './types'
import { DEMO_ACT_VERSIONS, DEMO_CORPUS_AS_OF } from './demo/acts'
import { NOT_COVERED_EN, QA_EN, SUGGESTED_QUESTIONS_EN } from './demo/qa-en'
import { NOT_COVERED_IT, QA_IT, SUGGESTED_QUESTIONS_IT } from './demo/qa-it'
import type { DemoQAResponse, DemoQAScenario } from './demo/types'

export { DEMO_ACT_VERSIONS, DEMO_CORPUS_AS_OF } from './demo/acts'
export { DEMO_ALERTS, DEMO_ALERT_SUMMARY, getDemoAlerts } from './demo/alerts'
export { DEMO_CLIENTS } from './demo/clients'
export { getMockGapAnalysis } from './demo/gap'
export { demoLanguage } from './demo/language'
export { getMockMonitorResponse } from './demo/monitor'
export type { DemoCitation, DemoProfile, DemoQAResponse, DemoQAScenario } from './demo/types'

// ─── Who is signed in ───────────────────────────────────────

/** The demo user: an invented consultant of an invented firm ("Esempio" is Italian for "example"). */
export const DEMO_USER: User = {
  id: 'demo-user-001',
  email: 'giulia@studio-esempio.example',
  name: 'Giulia Esempio',
  role: 'admin',
  organization_name: 'Studio Esempio Associati (demo)',
}

export const DEMO_TOKENS: TokenPair = {
  access_token: 'demo.jwt.token',
  refresh_token: 'demo.refresh.token',
  token_type: 'bearer',
  expires_in: 3600,
}

// ─── System ─────────────────────────────────────────────────

/**
 * What GET /api/v1/stats answers in the demo: the shape of the real answer
 * with nothing that reads as a live server. No "healthy", no model, no
 * request counters. The administration page does not show it at all in the
 * demo (components/admin/SystemStatusSection.tsx).
 */
export const DEMO_STATS: SystemStats = {
  status: 'demo',
  version: 'demo',
  environment: 'demo',
  llm_provider: '',
  llm_model: '',
  timestamp: `${DEMO_CORPUS_AS_OF}T00:00:00Z`,
  qdrant_available: false,
  llm_available: false,
  metrics: { total_requests: 0, error_count: 0, endpoints: {} },
}

/** What GET /api/v1/processors answers in the demo: no document is processed. */
export const DEMO_PROCESSORS = {
  status: 'demo',
  engines: [] as string[],
  dots_ocr: { available: false },
  docling: { available: false },
}

// ─── Chiedi ─────────────────────────────────────────────────

const QA: Record<Language, Record<DemoQAScenario, DemoQAResponse>> = { it: QA_IT, en: QA_EN }

const MENTIONS_AI =
  /\bai act\b|intelligenza artificiale|artificial intelligence|\b(?:l|un|dell|all|sull|nell)['\u2019]ia\b|\bsistem[ai] di ia\b|\bai (?:systems?|literacy|tools?|models?)\b|\b(?:an|use|uses|using) ai\b/

/** The example a question is about, or null when the demo has none for it. */
export function qaScenarioOf(question: string): DemoQAScenario | null {
  const q = question.toLowerCase()
  const has = (...words: string[]) => words.some((w) => q.includes(w))
  const article = Number(q.match(/\bart(?:\.|icol[oi]|icles?)?\s*(\d{1,3})\b/)?.[1] ?? 0)
  const ai = MENTIONS_AI.test(q)
  const gdpr = has('gdpr', 'protezione dati', 'protezione dei dati', 'data protection', 'privacy')
  const dora = /\bdora\b/.test(q)
  const nis2 = /\bnis ?2\b/.test(q)

  // One article of one act.
  if ((article === 17 && gdpr) || has('diritto alla cancellazione', "diritto all'oblio", 'right to erasure', 'right to be forgotten'))
    return 'gdpr_art17'
  if (article === 13 && gdpr) return 'gdpr_art13'
  if ((article === 9 && gdpr) || has('dati sensibili', 'categorie particolari', 'special categories', 'dati biometrici', 'dati genetici', 'dati sanitari', 'health data'))
    return 'gdpr_art9'
  if (article === 9 && ai) return 'ai_act_art9'
  if (article === 30 && dora) return 'dora_art30'
  if ((article === 4 && ai) || has('alfabetizzazione', 'ai literacy') || (ai && has('formare', 'formazione', 'train')))
    return 'ai_act_art4'

  // Systems that talk to people (the example of the landing page).
  if (has('chatbot', 'assistente virtuale', 'virtual assistant', 'deepfake') || (ai && (article === 50 || has('trasparenza', 'transparency', 'dichiarare', 'marcatura', 'watermark'))))
    return 'ai_act_art50'

  // What a large customer may ask a smaller supplier.
  if (has('questionari', 'questionnaire', 'catena del valore', 'value chain', 'impresa protetta', 'protected undertaking', 'principi volontari', 'voluntary standard', 'vsme'))
    return 'value_chain'

  // Two acts together.
  if (ai && (gdpr || has('credit scor', 'merito di credito', 'creditworth'))) return 'cross_ai_gdpr'
  if (dora && (nis2 || has('sicurezza informatica', 'cybersecurity'))) return 'cross_dora_nis2'

  if (has('dpo', 'data protection officer', 'responsabile della protezione', 'responsabile protezione')) return 'gdpr_dpo'

  // One act.
  if (ai || has('alto rischio', 'high-risk', 'high risk')) return 'ai_act'
  if (gdpr || has('dati personali', 'personal data')) return 'gdpr'
  if (dora || has('digital operational', 'resilienza operativa')) return 'dora'
  if (nis2 || has('cybersecurity', 'cybersicurezza', 'cibersicurezza', 'sicurezza informatica')) return 'nis2'
  if (has('taxonomy', 'tassonomia', 'ecosostenibil', 'environmentally sustainable')) return 'taxonomy'
  if (has('csddd', 'due diligence', 'dovere di diligenza', 'catena di attività', 'supply chain')) return 'csddd'
  if (has('csrd', 'sustainability reporting', 'rendicontazione', 'omnibus', 'esrs', 'sostenibilità')) return 'csrd'
  return null
}

/**
 * The demo answer to a question, in the language asked for ("it" or "en";
 * anything else is answered in Italian). A question the demo has no example
 * for gets an abstention, never an invented answer.
 */
export function getMockQAResponse(question: string, language: string = 'it'): DemoQAResponse {
  const lang: Language = language === 'en' ? 'en' : 'it'
  const scenario = qaScenarioOf(question)

  if (!scenario) {
    return {
      answer: lang === 'en' ? NOT_COVERED_EN : NOT_COVERED_IT,
      citations: [],
      confidence_score: 0.0,
      requires_expert_review: false,
      related_frameworks: [],
      caveats: [],
      abstention_reason: 'demo_not_covered',
      suggested_questions: lang === 'en' ? SUGGESTED_QUESTIONS_EN : SUGGESTED_QUESTIONS_IT,
      corpus_as_of: DEMO_CORPUS_AS_OF,
    }
  }

  const response = QA[lang][scenario]
  return {
    ...response,
    // A verified passage of an amended act says which consolidated text it was read in.
    citations: response.citations.map((c) =>
      c.verified && c.celex && DEMO_ACT_VERSIONS[c.celex] ? { ...c, consolidated_as_of: DEMO_ACT_VERSIONS[c.celex] } : c,
    ),
    corpus_as_of: DEMO_CORPUS_AS_OF,
  }
}

// ─── Delay helper ───────────────────────────────────────────

export function mockDelay(ms: number = 1500): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms))
}
