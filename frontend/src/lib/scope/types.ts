import type { Source } from '@/lib/sources'

export type ScopeStatus = 'in_scope' | 'out_of_scope' | 'conditional' | 'not_assessed'

export type ScopeFramework = 'CSRD' | 'CSDDD' | 'AI_ACT'

export type GroupRole = 'standalone' | 'parent' | 'subsidiary'

/** The four situations of public/scope-aiact.html, in the same order. */
export interface AiActAnswers {
  /** A system that interacts directly with people (chatbot, voicebot). */
  interactsWithPeople: boolean
  /** Generates synthetic text, images, audio or video. */
  generatesSyntheticContent: boolean
  /** Emotion recognition or biometric categorisation. */
  emotionOrBiometric: boolean
  /** Deepfakes or AI-generated texts published to inform the public. */
  deepfakeOrPublicText: boolean
}

export type AiKey = 'chat' | 'gen' | 'emo' | 'deep'

export const AI_KEY_FIELD: Record<AiKey, keyof AiActAnswers> = {
  chat: 'interactsWithPeople',
  gen: 'generatesSyntheticContent',
  emo: 'emotionOrBiometric',
  deep: 'deepfakeOrPublicText',
}

export interface ScopeInput {
  name?: string
  /** Average number of employees in the year. */
  employees: number | null
  /** Net annual turnover in euro. */
  turnoverEur: number | null
  /** Listed on an EU regulated market. */
  listedEu: boolean
  /** Already reporting under NFRD / CSRD wave 1 (FY2024). */
  wave1Reporter: boolean
  groupRole: GroupRole
  /** Company domiciled outside the EU. */
  nonEu: boolean
  /** Net turnover generated in the EU, used only when nonEu is true. */
  euTurnoverEur: number | null
  sector?: string
  /** ISO 3166-1 alpha-2 country code. */
  country?: string
  /** null means the AI questions were not answered: the AI Act is then not assessed. */
  ai: AiActAnswers | null
}

/** An exact passage of law, rendered with LawQuote. */
export interface LegalPassage {
  quote: string
  before?: string
  after?: string
  act: string
  article: string
  celex?: string
  url?: string
}

/** One article 50 obligation, as the AI Act checker describes it. */
export interface AiObligation {
  key: AiKey
  who: 'provider' | 'deployer'
  whoLabel: string
  title: string
  requirement: string
  exception: string
  article: string
  source: Source
}

export interface ScopeResult {
  framework: ScopeFramework
  status: ScopeStatus
  /** One-line verdict shown under the badge. */
  headline: string
  /** ISO application date, when the sources state one. */
  from?: string
  /** Human label for `from`, e.g. "Soglie in vigore dal 18 marzo 2026". */
  fromLabel?: string
  /** Plain Italian reasons, in reading order. */
  reasons: string[]
  /** Secondary notes: exemptions, indirect pressure, what to verify. */
  notes: string[]
  sources: Source[]
  passages: LegalPassage[]
  obligations?: AiObligation[]
  verifiedOn: string
}

export interface ScopeAssessment {
  input: ScopeInput
  results: ScopeResult[]
  verifiedOn: string
}
