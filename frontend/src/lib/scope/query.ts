/**
 * The scope form state travels in the query string so a result can be
 * shared internally as a link. Keys are short Italian words; numbers are
 * plain integers; the AI answers are a comma list of keys or "nessuna".
 */
import type { AiActAnswers, AiKey, GroupRole, ScopeInput } from './types'
import { AI_KEY_FIELD } from './types'

export const EMPTY_INPUT: ScopeInput = {
  name: '',
  employees: null,
  turnoverEur: null,
  listedEu: false,
  wave1Reporter: false,
  groupRole: 'standalone',
  nonEu: false,
  euTurnoverEur: null,
  sector: '',
  country: 'IT',
  ai: null,
}

export const NO_AI: AiActAnswers = {
  interactsWithPeople: false,
  generatesSyntheticContent: false,
  emotionOrBiometric: false,
  deepfakeOrPublicText: false,
}

const AI_KEYS: AiKey[] = ['chat', 'gen', 'emo', 'deep']
const GROUP_ROLES: GroupRole[] = ['standalone', 'parent', 'subsidiary']

export function aiToKeys(ai: AiActAnswers): AiKey[] {
  return AI_KEYS.filter((k) => ai[AI_KEY_FIELD[k]])
}

export function keysToAi(keys: AiKey[]): AiActAnswers {
  const ai = { ...NO_AI }
  for (const k of keys) ai[AI_KEY_FIELD[k]] = true
  return ai
}

export function inputToQuery(input: ScopeInput): URLSearchParams {
  const p = new URLSearchParams()
  if (input.name?.trim()) p.set('nome', input.name.trim())
  if (input.employees != null) p.set('dip', String(Math.round(input.employees)))
  if (input.turnoverEur != null) p.set('ricavi', String(Math.round(input.turnoverEur)))
  if (input.listedEu) p.set('quotata', '1')
  if (input.wave1Reporter) p.set('wave1', '1')
  if (input.groupRole !== 'standalone') p.set('gruppo', input.groupRole)
  if (input.nonEu) {
    p.set('extraue', '1')
    if (input.euTurnoverEur != null) p.set('ricaviue', String(Math.round(input.euTurnoverEur)))
  }
  if (input.sector?.trim()) p.set('settore', input.sector.trim())
  if (input.country) p.set('paese', input.country)
  if (input.ai) {
    const keys = aiToKeys(input.ai)
    p.set('ia', keys.length ? keys.join(',') : 'nessuna')
  }
  return p
}

function num(value: string | null): number | null {
  if (value == null || value === '') return null
  const n = Number(value)
  return Number.isFinite(n) && n >= 0 ? n : null
}

/** Rebuilds the input from a query string. Returns null when the query carries nothing to assess. */
export function queryToInput(query: URLSearchParams | string): ScopeInput | null {
  const p = typeof query === 'string' ? new URLSearchParams(query) : query
  const hasAnything = ['dip', 'ricavi', 'ricaviue', 'ia'].some((k) => p.has(k))
  if (!hasAnything) return null

  const role = p.get('gruppo')
  const ia = p.get('ia')
  let ai: AiActAnswers | null = null
  if (ia != null) {
    const keys = ia
      .split(',')
      .map((k) => k.trim())
      .filter((k): k is AiKey => (AI_KEYS as string[]).includes(k))
    ai = keysToAi(keys)
  }

  return {
    name: p.get('nome') ?? '',
    employees: num(p.get('dip')),
    turnoverEur: num(p.get('ricavi')),
    listedEu: p.get('quotata') === '1',
    wave1Reporter: p.get('wave1') === '1',
    groupRole: role && (GROUP_ROLES as string[]).includes(role) ? (role as GroupRole) : 'standalone',
    nonEu: p.get('extraue') === '1',
    euTurnoverEur: num(p.get('ricaviue')),
    sector: p.get('settore') ?? '',
    country: p.get('paese') ?? 'IT',
    ai,
  }
}
