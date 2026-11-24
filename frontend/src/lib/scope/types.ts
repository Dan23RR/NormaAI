import type { Source } from '@/lib/sources'

export type ScopeStatus = 'in_scope' | 'out_of_scope' | 'conditional' | 'not_assessed'

/**
 * The rule sets of the scope engine. AI_WORK: employers who use AI with
 * their workers; NIS2: the Italian NIS decree; MACHINERY: the Machinery
 * Regulation.
 */
export type ScopeFramework = 'CSRD' | 'CSDDD' | 'AI_ACT' | 'AI_WORK' | 'NIS2' | 'MACHINERY'

export type GroupRole = 'standalone' | 'parent' | 'subsidiary'

/** The four situations of Article 50 of the AI Act. */
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

/** How an employer uses AI with its workers. */
export interface WorkAiAnswers {
  /** AI contributes to decisions on hiring, changes, termination, discipline or performance. */
  decisions: boolean
  /** AI affects work organisation, pace, how work is done or safety-relevant decisions. */
  organisation: boolean
  /** Staff use AI tools in their work. */
  staffUse: boolean
  /** An intellectual profession that uses AI for its clients' work. */
  professional: boolean
  /** A system infers the emotions of workers. */
  emotions: boolean
}

export type WorkKey = 'dec' | 'org' | 'uso' | 'prof' | 'emo'

export const WORK_KEY_FIELD: Record<WorkKey, keyof WorkAiAnswers> = {
  dec: 'decisions',
  org: 'organisation',
  uso: 'staffUse',
  prof: 'professional',
  emo: 'emotions',
}

/** Sectors of annexes I and II of D.Lgs. 138/2024, in the order of the annexes. */
export const NIS_ANNEX_I = [
  'energia',
  'trasporti',
  'banche',
  'mercati',
  'sanita',
  'acqua',
  'reflue',
  'digitale',
  'tic',
  'spazio',
] as const
export const NIS_ANNEX_II = ['postali', 'rifiuti', 'chimica', 'alimenti', 'fabbricazione', 'servizi-digitali', 'ricerca'] as const

/** `pa`: a public administration of annex III; `altri`: a type of entity of annex IV; `nessuno`: none of them. */
export type NisSector = (typeof NIS_ANNEX_I)[number] | (typeof NIS_ANNEX_II)[number] | 'pa' | 'altri' | 'nessuno'

export const NIS_SECTORS: NisSector[] = [...NIS_ANNEX_I, ...NIS_ANNEX_II, 'pa', 'altri', 'nessuno']

export interface NisAnswers {
  sector: NisSector
  /** One of the providers the decree covers whatever their size (Art. 3(5)(b) to (e)). */
  anySize: boolean
  /** Linked to a NIS entity and running its systems, security or ICT services (Art. 3(10)). */
  linked: boolean
}

/** The roles of the Machinery Regulation. */
export interface MachineryAnswers {
  /** Builds machinery, related products or partly completed machinery, or sells them under its own name. */
  manufacturer: boolean
  /** Places on the Union market products from a third country. */
  importer: boolean
  /** Makes products available on the market without being manufacturer or importer. */
  distributor: boolean
  /** Substantially modifies machinery already on the market or in service. */
  modifier: boolean
}

export type MachineryKey = 'fab' | 'imp' | 'dis' | 'mod'

export const MACHINERY_KEY_FIELD: Record<MachineryKey, keyof MachineryAnswers> = {
  fab: 'manufacturer',
  imp: 'importer',
  dis: 'distributor',
  mod: 'modifier',
}

export interface ScopeInput {
  name?: string
  /** Average number of employees in the year. */
  employees: number | null
  /** Net annual turnover in euro. */
  turnoverEur: number | null
  /** Balance sheet total in euro: with employees and turnover it decides the size class (NIS). */
  balanceSheetEur: number | null
  /** Listed on an EU regulated market. */
  listedEu: boolean
  /** Already reporting on sustainability (large public-interest entity, financial years from 2024). */
  wave1Reporter: boolean
  groupRole: GroupRole
  /** Company domiciled outside the EU. */
  nonEu: boolean
  /** Net turnover generated in the EU, used only when nonEu is true. */
  euTurnoverEur: number | null
  sector?: string
  /** ISO 3166-1 alpha-2 country code. */
  country?: string
  /** null means the questions were not answered: the rule set is then not assessed. */
  ai: AiActAnswers | null
  work: WorkAiAnswers | null
  nis: NisAnswers | null
  machinery: MachineryAnswers | null
}

/** One duty of a rule set, with the provision that sets it. */
export interface ScopeObligation {
  key: string
  /** Who bears the duty: provider, deployer, employer, professional, manufacturer... */
  who: string
  whoLabel: string
  title: string
  requirement: string
  /** Exceptions, limits, deadlines: what to keep in mind next to the duty. */
  exception?: string
  article: string
  source: Source
}

/** One Article 50 obligation of the AI Act. */
export interface AiObligation extends ScopeObligation {
  key: AiKey
  who: 'provider' | 'deployer'
  exception: string
}

export interface ScopeResult {
  framework: ScopeFramework
  status: ScopeStatus
  /** One-line verdict shown under the badge. */
  headline: string
  /** ISO application date, when the sources state one. */
  from?: string
  /** Human label for `from`, e.g. "Si applica dal 20 gennaio 2027 (art. 54)". */
  fromLabel?: string
  /** Plain reasons, in reading order, in the language of the interface. */
  reasons: string[]
  /** Secondary notes: exemptions, indirect pressure, what to verify. */
  notes: string[]
  /** Every provision the verdict, the notes and the duties rely on. */
  sources: Source[]
  obligations?: ScopeObligation[]
}

export interface ScopeAssessment {
  input: ScopeInput
  results: ScopeResult[]
}
