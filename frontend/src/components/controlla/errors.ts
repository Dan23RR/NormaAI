import { ApiError } from '@/lib/api-error'
import { InvalidCheckResponse } from './documents-api'

/**
 * What went wrong with a call to the documents API, in terms the page can
 * explain: every kind has a sentence in the `controlla.errors` messages that
 * says what happened and what to do next. The server adds a sentence of its
 * own in Italian (`detail`), which the page shows under ours.
 */
export const FAILURE_KINDS = [
  'tooLarge',
  'unsupported',
  'unreadable',
  'rateLimited',
  'timeout',
  'full',
  'forbidden',
  'notFound',
  'missingApi',
  'rejected',
  'server',
  'network',
  'session',
  'invalid',
  'generic',
] as const
export type FailureKind = (typeof FAILURE_KINDS)[number]

export interface Failure {
  kind: FailureKind
  /** HTTP status, when the server answered. */
  status?: number
  /** The server's own sentence, shown under ours when it adds something. */
  detail?: string
}

/**
 * What the call was doing. 413, 415 and 422 speak of the document only when
 * one was being sent; on any other call they are a request the server refused.
 */
export type FailureContext = 'check' | 'other'

/** What a server without the route answers: the documents API is not there. */
const ROUTE_MISSING = 'Not Found'

/** The HTTP status carried by an API error, when the server answered with one. */
export function httpStatusOf(err: unknown): number | undefined {
  if (!(err instanceof ApiError) || err.code !== 'requestFailed') return undefined
  const status = Number(err.values?.status)
  return Number.isInteger(status) && status > 0 ? status : undefined
}

function kindOf(status: number, detail: string | undefined, context: FailureContext): FailureKind {
  if (status === 404) {
    if (detail === ROUTE_MISSING) return 'missingApi'
    // While sending a document, what is "not found" is the client chosen for it.
    return context === 'check' ? 'rejected' : 'notFound'
  }
  if (status === 403) return 'forbidden'
  if (status === 409) return 'full'
  if (status === 429) return 'rateLimited'
  if (status === 408 || status === 504) return 'timeout'
  if (status >= 500) return 'server'
  if (context === 'check') {
    if (status === 413) return 'tooLarge'
    if (status === 415) return 'unsupported'
    if (status === 422) return 'unreadable'
  }
  return 'rejected'
}

export function describeFailure(err: unknown, context: FailureContext = 'other'): Failure {
  if (err instanceof InvalidCheckResponse) return { kind: 'invalid' }
  if (!(err instanceof ApiError)) return { kind: 'generic' }
  if (err.code === 'network') return { kind: 'network' }
  if (err.code === 'sessionExpired' || err.code === 'unauthorized') return { kind: 'session' }
  const status = httpStatusOf(err)
  if (status === undefined) return { kind: 'generic', detail: err.detail }
  const kind = kindOf(status, err.detail, context)
  // "Not Found" says nothing to a person: our sentence already tells what it means.
  return { kind, status, detail: kind === 'missingApi' ? undefined : err.detail }
}

/**
 * True when the check asked for does not exist: deleted, never there, or an
 * address that is not the id of a check (the server answers 422 to that).
 */
export function isMissingCheck(err: unknown): boolean {
  const status = httpStatusOf(err)
  if (status === 422) return true
  return status === 404 && (err as ApiError).detail !== ROUTE_MISSING
}
