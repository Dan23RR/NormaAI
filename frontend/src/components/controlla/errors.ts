import { ApiError } from '@/lib/api-error'
import { InvalidCheckResponse } from './documents-api'

/**
 * What went wrong with a call to the documents API, in terms the page can
 * explain: every kind has a sentence in the `controlla.errors` messages that
 * says what happened and what to do next.
 */
export const FAILURE_KINDS = [
  'tooLarge',
  'unsupported',
  'unreadable',
  'rateLimited',
  'timeout',
  'notFound',
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

const BY_STATUS: Record<number, FailureKind> = {
  404: 'notFound',
  408: 'timeout',
  413: 'tooLarge',
  415: 'unsupported',
  422: 'unreadable',
  429: 'rateLimited',
  504: 'timeout',
}

/** The HTTP status carried by an API error, when the server answered with one. */
export function httpStatusOf(err: unknown): number | undefined {
  if (!(err instanceof ApiError) || err.code !== 'requestFailed') return undefined
  const status = Number(err.values?.status)
  return Number.isInteger(status) && status > 0 ? status : undefined
}

export function describeFailure(err: unknown): Failure {
  if (err instanceof InvalidCheckResponse) return { kind: 'invalid' }
  if (!(err instanceof ApiError)) return { kind: 'generic' }
  if (err.code === 'network') return { kind: 'network' }
  if (err.code === 'sessionExpired' || err.code === 'unauthorized') return { kind: 'session' }
  const status = httpStatusOf(err)
  if (status === undefined) return { kind: 'generic', detail: err.detail }
  const kind: FailureKind = BY_STATUS[status] ?? (status >= 500 ? 'server' : 'rejected')
  return { kind, status, detail: err.detail }
}

/** True when the check asked for does not exist (deleted, or never there). */
export function isNotFound(err: unknown): boolean {
  return httpStatusOf(err) === 404
}
