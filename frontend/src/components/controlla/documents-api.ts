import { api } from '@/lib/api'
import {
  DEPENDENCY_STATES,
  GROUPS,
  isGroup,
  type CheckCounts,
  type CheckList,
  type CheckSummary,
  type Dependency,
  type DependencyState,
  type Difference,
  type DocumentCheck,
  type DocumentPreferences,
  type Finding,
  type FindingGroup,
} from './types'

/**
 * The documents API (src/api/routers/documents.py), prefix /api/v1/documents.
 *
 * - POST   /check                      multipart (`file`) or JSON ({text, filename}); optional
 *                                      client_id, document_date (ISO), watch -> the check
 * - GET    /checks?client_id=&needs_review=&limit=&offset=  -> {items: summary[], total}
 * - GET    /checks/{id}                -> the check
 * - DELETE /checks/{id}                -> 204
 * - POST   /checks/{id}/recheck        -> the check after its provisions were compared again
 * - GET    /checks/{id}/report         -> the report, as an HTML page
 * - GET, PATCH /preferences            -> {email_digest}
 *
 * The file is read in memory and not stored. In the demo the api client
 * answers these routes from src/lib/mock-documents.ts.
 */
const BASE = '/api/v1/documents'

/** The formats and the size the check reads (a PDF needs a text layer). */
export const ACCEPTED_EXTENSIONS = ['.docx', '.pdf', '.html', '.txt', '.md'] as const
export const MAX_FILE_BYTES = 10 * 1024 * 1024

/** How many checks a page of the list asks for. */
export const PAGE_SIZE = 20

export function extensionOf(name: string): string {
  const index = name.lastIndexOf('.')
  return index >= 0 ? name.slice(index).toLowerCase() : ''
}

/** The server answered, but not with a check. */
export class InvalidCheckResponse extends Error {
  constructor() {
    super('invalid check response')
    this.name = 'InvalidCheckResponse'
  }
}

// ─── Reading what the server sends ──────────────────────────
// The backend is developed next to this page: a field left out must never
// take the screen down, so every list and every optional value is settled here.

type Raw = Record<string, unknown>

const isRecord = (value: unknown): value is Raw => !!value && typeof value === 'object' && !Array.isArray(value)
const text = (value: unknown): string => (typeof value === 'string' ? value : '')
const textOrNull = (value: unknown): string | null => (typeof value === 'string' && value.trim() ? value : null)
const count = (value: unknown): number => (typeof value === 'number' && Number.isFinite(value) && value > 0 ? Math.floor(value) : 0)
const strings = (value: unknown): string[] => (Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string' && v.trim() !== '') : [])

function asDifferences(value: unknown): Difference[] {
  if (!Array.isArray(value)) return []
  return value
    .filter(isRecord)
    .map((d) => ({ quoted: text(d.quoted), official: text(d.official) }))
    .filter((d) => d.quoted || d.official)
}

function asFinding(value: unknown, index: number): Finding | null {
  if (!isRecord(value)) return null
  const status = isRecord(value.status) ? value.status : {}
  const act = isRecord(value.act) ? value.act : null
  const provision = isRecord(value.provision) ? value.provision : null
  const version = isRecord(value.version) ? value.version : null
  const before = isRecord(value.before) && text(value.before.text).trim() ? value.before : null
  return {
    id: text(value.id) || `f${index + 1}`,
    group: isGroup(value.group) ? value.group : 'controllare',
    status: { code: text(status.code), label: text(status.label) },
    line: count(value.line),
    raw: text(value.raw),
    context: text(value.context),
    act: act && { source: text(act.source) || 'eurlex', id: text(act.id), name: text(act.name), label: text(act.label) },
    provision: provision && { key: text(provision.key), label: text(provision.label) },
    version: version && { id: text(version.id), as_of: textOrNull(version.as_of), label: text(version.label) },
    url: textOrNull(value.url),
    messages: strings(value.messages),
    quotes: strings(value.quotes),
    official_quote: textOrNull(value.official_quote),
    differences: asDifferences(value.differences),
    before: before && { version_label: text(before.version_label), text: text(before.text) },
    after_text: textOrNull(value.after_text),
  }
}

function asDependency(value: unknown): Dependency | null {
  if (!isRecord(value)) return null
  const state = (DEPENDENCY_STATES as readonly string[]).includes(text(value.state)) ? (value.state as DependencyState) : 'current'
  return {
    source: text(value.source) || 'eurlex',
    act: text(value.act),
    name: text(value.name),
    article: text(value.article),
    key: text(value.key),
    version: text(value.version),
    as_of: textOrNull(value.as_of),
    fingerprint: text(value.fingerprint),
    state,
    changed_at: textOrNull(value.changed_at),
  }
}

function asCounts(value: unknown): CheckCounts {
  const raw = isRecord(value) ? value : {}
  return { correggere: count(raw.correggere), controllare: count(raw.controllare), a_posto: count(raw.a_posto), non_coperto: count(raw.non_coperto) }
}

/** The worst group that has findings; a check without findings has nothing to correct. */
function worstGroup(counts: CheckCounts): FindingGroup {
  return GROUPS.find((group) => group !== 'non_coperto' && counts[group] > 0) ?? 'a_posto'
}

export function asSummary(value: unknown): CheckSummary | null {
  if (!isRecord(value) || !text(value.id)) return null
  const counts = asCounts(value.counts)
  return {
    id: text(value.id),
    client_id: textOrNull(value.client_id),
    filename: text(value.filename),
    document_sha256: text(value.document_sha256),
    document_date: textOrNull(value.document_date),
    checked_at: text(value.checked_at),
    lang: (text(value.lang) || 'IT').toUpperCase(),
    // Only an explicit false turns surveillance off: the contract's default is on.
    watch: value.watch !== false,
    status: isGroup(value.status) ? value.status : worstGroup(counts),
    needs_review: value.needs_review === true,
    counts,
  }
}

export function asCheck(value: unknown): DocumentCheck {
  const summary = asSummary(value)
  if (!summary) throw new InvalidCheckResponse()
  const raw = value as Raw
  const findings = (Array.isArray(raw.findings) ? raw.findings : []).map(asFinding).filter((f): f is Finding => f !== null)
  const dependencies = (Array.isArray(raw.dependencies) ? raw.dependencies : [])
    .map(asDependency)
    .filter((d): d is Dependency => d !== null)
  return { ...summary, findings, dependencies }
}

export function asList(value: unknown): CheckList {
  const rawItems = Array.isArray(value) ? value : isRecord(value) && Array.isArray(value.items) ? value.items : []
  const items = rawItems.map(asSummary).filter((s): s is CheckSummary => s !== null)
  const total = isRecord(value) && typeof value.total === 'number' ? value.total : items.length
  return { items, total: Math.max(total, items.length) }
}

// ─── Calls ──────────────────────────────────────────────────

export interface CheckOptions {
  clientId?: string | null
  /** ISO date (YYYY-MM-DD) the document bears. */
  documentDate?: string | null
  watch: boolean
}

/** Check a file. It travels as multipart with the options next to it. */
export async function checkFile(file: File, options: CheckOptions): Promise<DocumentCheck> {
  const form = new FormData()
  form.append('file', file)
  if (options.clientId) form.append('client_id', options.clientId)
  if (options.documentDate) form.append('document_date', options.documentDate)
  form.append('watch', options.watch ? 'true' : 'false')
  return asCheck(await api.upload<unknown>(`${BASE}/check`, form))
}

/** Check a pasted text; `filename` is the name it gets in the list. */
export async function checkText(body: string, filename: string, options: CheckOptions): Promise<DocumentCheck> {
  const payload: Raw = { text: body, filename, watch: options.watch }
  if (options.clientId) payload.client_id = options.clientId
  if (options.documentDate) payload.document_date = options.documentDate
  return asCheck(await api.post<unknown>(`${BASE}/check`, payload))
}

export interface ListQuery {
  clientId?: string
  needsReview?: boolean
  limit?: number
  offset?: number
}

export function listPath(query: ListQuery = {}): string {
  const params = new URLSearchParams()
  if (query.clientId) params.set('client_id', query.clientId)
  if (query.needsReview) params.set('needs_review', 'true')
  params.set('limit', String(query.limit ?? PAGE_SIZE))
  params.set('offset', String(query.offset ?? 0))
  return `${BASE}/checks?${params.toString()}`
}

export async function fetchChecks(query: ListQuery = {}): Promise<CheckList> {
  return asList(await api.get<unknown>(listPath(query)))
}

const checkPath = (id: string) => `${BASE}/checks/${encodeURIComponent(id)}`

export async function fetchCheck(id: string): Promise<DocumentCheck> {
  return asCheck(await api.get<unknown>(checkPath(id)))
}

/** Compare the provisions the check recorded with the text in force now. The file is not needed. */
export async function recheck(id: string): Promise<DocumentCheck> {
  return asCheck(await api.post<unknown>(`${checkPath(id)}/recheck`, {}))
}

export async function deleteCheck(id: string): Promise<void> {
  await api.del<unknown>(checkPath(id))
}

/** The report of a check: a self-contained HTML page written by the server. */
export async function fetchReportHtml(id: string): Promise<string> {
  const response = await api.fetchBlob(`${checkPath(id)}/report`)
  return response.text()
}

export async function fetchPreferences(): Promise<DocumentPreferences> {
  const raw = await api.get<unknown>(`${BASE}/preferences`)
  return { email_digest: isRecord(raw) && raw.email_digest === true }
}

export async function savePreferences(preferences: DocumentPreferences): Promise<DocumentPreferences> {
  const raw = await api.patch<unknown>(`${BASE}/preferences`, preferences)
  return { email_digest: isRecord(raw) ? raw.email_digest === true : preferences.email_digest }
}

// ─── From the form to the page of the check ─────────────────
// POST /check already answers with the whole check: the page it opens reads
// it from here instead of asking the server again.

export interface FreshCheck {
  check: DocumentCheck
  /** True when the demo answered with its example instead of reading the file. */
  example: boolean
}

const FRESH_FOR_MS = 2 * 60 * 1000
let fresh: (FreshCheck & { at: number }) | null = null

export function rememberCheck(check: DocumentCheck, example: boolean): void {
  fresh = { check, example, at: Date.now() }
}

/** The check the form just received, for a couple of minutes (reading it does not consume it). */
export function recallCheck(id: string): FreshCheck | undefined {
  if (!fresh || fresh.check.id !== id || Date.now() - fresh.at > FRESH_FOR_MS) return undefined
  return { check: fresh.check, example: fresh.example }
}

export function forgetCheck(id?: string): void {
  if (!id || fresh?.check.id === id) fresh = null
}
