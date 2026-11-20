/**
 * The one dated status line of the site ("the application server is being
 * moved, accounts are suspended"), shared by the sign-in, security and method
 * pages so that they cannot contradict each other.
 */

/**
 * True when a backend origin is configured for this build. Same rule as
 * `API_CONFIGURED` in lib/api.ts (a test keeps the two equal), kept here so
 * that server pages do not import the browser API client to read one flag.
 * The status line is shown only while this is false: it disappears by itself
 * when the server is back and NEXT_PUBLIC_API_BASE_URL is set again.
 */
export const BACKEND_CONFIGURED = (process.env.NEXT_PUBLIC_API_BASE_URL || '') !== ''

/**
 * The day the wording of the status line was last checked against reality
 * (UTC midnight; formatted per language by the pages). Change it whenever the
 * status is confirmed again: the line never promises a return date.
 */
export const SERVICE_STATUS_ON = new Date(Date.UTC(2026, 10, 11))
