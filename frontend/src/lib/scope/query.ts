/**
 * The scope form state travels in the query string so a result can be
 * shared internally as a link. Keys are short Italian words; numbers are
 * plain integers; each group of answers is a comma list of keys, or
 * "nessuna" when the question was answered with "none of these".
 */
import type {
  AiActAnswers,
  AiKey,
  GroupRole,
  MachineryAnswers,
  MachineryKey,
  NisAnswers,
  NisSector,
  ScopeInput,
  WorkAiAnswers,
  WorkKey,
} from './types'
import { AI_KEY_FIELD, MACHINERY_KEY_FIELD, NIS_SECTORS, WORK_KEY_FIELD } from './types'

export const EMPTY_INPUT: ScopeInput = {
  name: '',
  employees: null,
  turnoverEur: null,
  balanceSheetEur: null,
  listedEu: false,
  wave1Reporter: false,
  groupRole: 'standalone',
  nonEu: false,
  euTurnoverEur: null,
  sector: '',
  country: 'IT',
  ai: null,
  work: null,
  nis: null,
  machinery: null,
}

export const NO_AI: AiActAnswers = {
  interactsWithPeople: false,
  generatesSyntheticContent: false,
  emotionOrBiometric: false,
  deepfakeOrPublicText: false,
}

export const NO_WORK_AI: WorkAiAnswers = {
  decisions: false,
  organisation: false,
  staffUse: false,
  professional: false,
  emotions: false,
}

export const NO_MACHINERY: MachineryAnswers = {
  manufacturer: false,
  importer: false,
  distributor: false,
  modifier: false,
}

/** The answer "none of these sectors, no special case". */
export const NO_NIS: NisAnswers = { sector: 'nessuno', anySize: false, linked: false }

const NONE = 'nessuna'
const AI_KEYS: AiKey[] = ['chat', 'gen', 'emo', 'deep']
const WORK_KEYS: WorkKey[] = ['dec', 'org', 'uso', 'prof', 'emo']
const MACHINERY_KEYS: MachineryKey[] = ['fab', 'imp', 'dis', 'mod']
const GROUP_ROLES: GroupRole[] = ['standalone', 'parent', 'subsidiary']

function toKeys<K extends string, A>(all: K[], fields: Record<K, keyof A>, answers: A): K[] {
  return all.filter((k) => Boolean(answers[fields[k]]))
}

function fromKeys<K extends string, A>(none: A, fields: Record<K, keyof A>, keys: K[]): A {
  const answers = { ...none } as Record<keyof A, boolean>
  for (const k of keys) answers[fields[k]] = true
  return answers as A
}

export function aiToKeys(ai: AiActAnswers): AiKey[] {
  return toKeys(AI_KEYS, AI_KEY_FIELD, ai)
}

export function keysToAi(keys: AiKey[]): AiActAnswers {
  return fromKeys(NO_AI, AI_KEY_FIELD, keys)
}

export function workToKeys(work: WorkAiAnswers): WorkKey[] {
  return toKeys(WORK_KEYS, WORK_KEY_FIELD, work)
}

export function keysToWork(keys: WorkKey[]): WorkAiAnswers {
  return fromKeys(NO_WORK_AI, WORK_KEY_FIELD, keys)
}

export function machineryToKeys(machinery: MachineryAnswers): MachineryKey[] {
  return toKeys(MACHINERY_KEYS, MACHINERY_KEY_FIELD, machinery)
}

export function keysToMachinery(keys: MachineryKey[]): MachineryAnswers {
  return fromKeys(NO_MACHINERY, MACHINERY_KEY_FIELD, keys)
}

function listParam<K extends string>(keys: K[]): string {
  return keys.length ? keys.join(',') : NONE
}

function parseList<K extends string>(value: string, all: K[]): K[] {
  return value
    .split(',')
    .map((k) => k.trim())
    .filter((k): k is K => (all as string[]).includes(k))
}

export function inputToQuery(input: ScopeInput): URLSearchParams {
  const p = new URLSearchParams()
  if (input.name?.trim()) p.set('nome', input.name.trim())
  if (input.employees != null) p.set('dip', String(Math.round(input.employees)))
  if (input.turnoverEur != null) p.set('ricavi', String(Math.round(input.turnoverEur)))
  if (input.balanceSheetEur != null) p.set('bilancio', String(Math.round(input.balanceSheetEur)))
  if (input.listedEu) p.set('quotata', '1')
  if (input.wave1Reporter) p.set('wave1', '1')
  if (input.groupRole !== 'standalone') p.set('gruppo', input.groupRole)
  if (input.nonEu) {
    p.set('extraue', '1')
    if (input.euTurnoverEur != null) p.set('ricaviue', String(Math.round(input.euTurnoverEur)))
  }
  if (input.sector?.trim()) p.set('settore', input.sector.trim())
  if (input.country) p.set('paese', input.country)
  if (input.ai) p.set('ia', listParam(aiToKeys(input.ai)))
  if (input.work) p.set('lav', listParam(workToKeys(input.work)))
  if (input.nis) {
    p.set('nis', input.nis.sector)
    if (input.nis.anySize) p.set('nisdim', '1')
    if (input.nis.linked) p.set('niscoll', '1')
  }
  if (input.machinery) p.set('mac', listParam(machineryToKeys(input.machinery)))
  return p
}

function num(value: string | null): number | null {
  if (value == null || value === '') return null
  const n = Number(value)
  return Number.isFinite(n) && n >= 0 ? n : null
}

/** Keys that carry something to assess: without one of them the query is only a profile. */
const ASSESSABLE = ['dip', 'ricavi', 'ricaviue', 'ia', 'lav', 'nis', 'mac']

/** Rebuilds the input from a query string. Returns null when the query carries nothing to assess. */
export function queryToInput(query: URLSearchParams | string): ScopeInput | null {
  const p = typeof query === 'string' ? new URLSearchParams(query) : query
  if (!ASSESSABLE.some((k) => p.has(k))) return null

  const role = p.get('gruppo')
  const ia = p.get('ia')
  const lav = p.get('lav')
  const mac = p.get('mac')
  const nisSector = p.get('nis')
  const nis: NisAnswers | null =
    nisSector != null && (NIS_SECTORS as string[]).includes(nisSector)
      ? { sector: nisSector as NisSector, anySize: p.get('nisdim') === '1', linked: p.get('niscoll') === '1' }
      : null

  return {
    name: p.get('nome') ?? '',
    employees: num(p.get('dip')),
    turnoverEur: num(p.get('ricavi')),
    balanceSheetEur: num(p.get('bilancio')),
    listedEu: p.get('quotata') === '1',
    wave1Reporter: p.get('wave1') === '1',
    groupRole: role && (GROUP_ROLES as string[]).includes(role) ? (role as GroupRole) : 'standalone',
    nonEu: p.get('extraue') === '1',
    euTurnoverEur: num(p.get('ricaviue')),
    sector: p.get('settore') ?? '',
    country: p.get('paese') ?? 'IT',
    ai: ia == null ? null : keysToAi(parseList(ia, AI_KEYS)),
    work: lav == null ? null : keysToWork(parseList(lav, WORK_KEYS)),
    nis,
    machinery: mac == null ? null : keysToMachinery(parseList(mac, MACHINERY_KEYS)),
  }
}
