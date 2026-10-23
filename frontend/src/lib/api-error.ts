/**
 * An error the API client raises on its own (no server detail to show):
 * the interface translates `code` through the `errors` namespace. When the
 * server answered with a `detail`, that text is shown as it came.
 */
export type ApiErrorCode =
  | 'network'
  | 'sessionExpired'
  | 'requestFailed'
  | 'loginFailed'
  | 'registerFailed'
  | 'uploadDemo'
  | 'reportDemo'
  | 'unauthorized'
  | 'invitesUnavailable'

export class ApiError extends Error {
  readonly code: ApiErrorCode
  readonly detail?: string
  readonly values?: Record<string, string | number>

  constructor(code: ApiErrorCode, opts: { detail?: string; values?: Record<string, string | number> } = {}) {
    super(opts.detail ?? code)
    this.name = 'ApiError'
    this.code = code
    this.detail = opts.detail
    this.values = opts.values
  }
}
