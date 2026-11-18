/**
 * Input checks and a per-IP limit for the lead route (src/app/api/leads/route.ts),
 * kept apart from it because a route module may export only its handlers.
 *
 * Every public form posts there: the Codex form of the home page and the two
 * static checkers (public/scope-aiact.html, public/scope-csrd.html). What they
 * send is short and known, so anything else is refused instead of being
 * passed on to the operator's inbox.
 */

/** Largest request body the route reads, in bytes: a lead is a few short fields. */
export const MAX_BODY_BYTES = 4096

/** Longest email address (RFC 5321: 254 characters in a path). */
const MAX_EMAIL = 254

// A conservative address: no spaces, quotes, angle brackets or commas, a
// domain of letters, digits and hyphens with a top-level domain of letters
// (punycode included). Real addresses outside it are rare in a work form.
const EMAIL_RE =
  /^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$/

// The values the forms send: "codex_download" from the home page;
// "aiact_checker:in:chat+gen" (the band, then the ticked situations in the
// page's order) and "aiact_checker:out" from the AI Act checker;
// "scope_checker:in|filo|out" from the CSRD checker.
const SITUATION = '(?:chat|gen|emo|deep)'
const SOURCE_RE = new RegExp(
  `^(?:codex_download|aiact_checker:(?:in|out)(?::${SITUATION}(?:\\+${SITUATION}){0,3})?|scope_checker:(?:in|filo|out))$`,
)

/** The roles the forms send: the options of the Codex form (in Italian, as the inbox reads them) and the two checkers. */
export const LEAD_ROLES: readonly string[] = [
  'Compliance officer / DPO',
  'CFO / Risk manager',
  'Avvocato / Consulente',
  'Altro',
  'aiact_checker',
  'scope_checker',
]

/** The id of an outreach email (/codex?lead=<id>) or the name of a checker page. */
const LEAD_REF_RE = /^[A-Za-z0-9_-]{1,64}$/

export type Lead = {
  email: string
  orgName: string | null
  role: string | null
  source: string
  leadRef: string | null
}

export type LeadCheck = { ok: true; lead: Lead } | { ok: false; field: 'body' | 'email' | 'source' }

/**
 * A free-text field as one plain line: control characters and line
 * separators become spaces (nothing can start a new line in a subject),
 * runs of space become one, and the result is cut to `max` characters.
 */
export function plainText(value: unknown, max: number): string {
  if (typeof value !== 'string') return ''
  return value
    .replace(/[\u0000-\u001F\u007F-\u009F\u2028\u2029]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, max)
}

/** True when a hidden field only programs fill in carries a value (`website` is the key of pages cached before the rename). */
export function honeypotFilled(body: Record<string, unknown>): boolean {
  return plainText(body.contact_time, 200) !== '' || plainText(body.website, 200) !== ''
}

/** The lead a request body describes, or the first field that makes it unacceptable. */
export function checkLead(body: unknown): LeadCheck {
  if (!body || typeof body !== 'object' || Array.isArray(body)) return { ok: false, field: 'body' }
  const b = body as Record<string, unknown>

  const email = typeof b.email === 'string' ? b.email.trim() : ''
  if (email.length > MAX_EMAIL || !EMAIL_RE.test(email)) return { ok: false, field: 'email' }

  const source = b.source === undefined || b.source === null || b.source === '' ? 'codex_download' : b.source
  if (typeof source !== 'string' || !SOURCE_RE.test(source)) return { ok: false, field: 'source' }

  // Optional fields: an unknown role or reference is dropped, not refused, so
  // a page cached before a change still gets its request through.
  const role = typeof b.role === 'string' && LEAD_ROLES.includes(b.role) ? b.role : null
  const ref = typeof b.lead_ref === 'string' ? b.lead_ref.trim() : ''
  const leadRef = LEAD_REF_RE.test(ref) ? ref : null
  const orgName = plainText(b.org_name, 200) || null

  return { ok: true, lead: { email, orgName, role, source, leadRef } }
}

/**
 * The address of the client. On Vercel the platform writes these headers
 * from the connection and overwrites what the client sends, so they cannot
 * be forged there; elsewhere the first X-Forwarded-For entry is only a hint.
 * Requests without any share the key "unknown".
 */
export function clientIp(headers: Headers): string {
  const value = headers.get('x-vercel-forwarded-for') ?? headers.get('x-real-ip') ?? headers.get('x-forwarded-for') ?? ''
  return value.split(',')[0].trim() || 'unknown'
}

export type RateLimit = { allowed: boolean; retryAfterSeconds: number }

export type RateLimiter = { hit(key: string, now?: number): RateLimit }

/**
 * A fixed-window counter per key, in the memory of one instance of the
 * function. Best effort by nature: a serverless function runs in several
 * instances, each with its own counters, and a cold start begins at zero.
 * It still stops one address from sending a stream of requests through a
 * warm instance. `maxKeys` bounds the memory: expired windows are dropped
 * first, then the oldest ones.
 */
export function createRateLimiter({
  limit,
  windowMs,
  maxKeys = 5000,
}: {
  limit: number
  windowMs: number
  maxKeys?: number
}): RateLimiter {
  const windows = new Map<string, { start: number; count: number }>()

  function makeRoom(now: number): void {
    for (const [key, window] of windows) {
      if (now - window.start >= windowMs) windows.delete(key)
    }
    while (windows.size >= maxKeys) {
      const oldest = windows.keys().next().value
      if (oldest === undefined) break
      windows.delete(oldest)
    }
  }

  return {
    hit(key: string, now: number = Date.now()): RateLimit {
      let window = windows.get(key)
      if (!window || now - window.start >= windowMs) {
        windows.delete(key)
        if (windows.size >= maxKeys) makeRoom(now)
        window = { start: now, count: 0 }
        windows.set(key, window)
      }
      window.count += 1
      if (window.count > limit) {
        return { allowed: false, retryAfterSeconds: Math.max(1, Math.ceil((window.start + windowMs - now) / 1000)) }
      }
      return { allowed: true, retryAfterSeconds: 0 }
    },
  }
}
