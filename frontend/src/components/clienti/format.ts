/**
 * Formatting for the application: Italian thousands separators, ISO dates
 * in tables, extended dates in running text (DESIGN.md, principle 2).
 */

// Italian CLDR data skips the separator on four-digit numbers ("5000"):
// in a column of figures every thousand gets its point, so grouping is forced.
const intFormatter = new Intl.NumberFormat('it-IT', { maximumFractionDigits: 0, useGrouping: 'always' })
const eurFormatter = new Intl.NumberFormat('it-IT', {
  style: 'currency',
  currency: 'EUR',
  maximumFractionDigits: 0,
  useGrouping: 'always',
})
const longDateFormatter = new Intl.DateTimeFormat('it-IT', {
  day: 'numeric',
  month: 'long',
  year: 'numeric',
})

/** Shown in a cell when the backend has no value for it. */
export const NOT_AVAILABLE = 'n.d.'

export function formatInt(value: number | null | undefined): string | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  return intFormatter.format(value)
}

export function formatEur(value: number | null | undefined): string | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  return eurFormatter.format(value)
}

function parseDate(iso: string | null | undefined): Date | null {
  if (!iso) return null
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? null : d
}

const pad = (n: number) => String(n).padStart(2, '0')

/** ISO date (YYYY-MM-DD) in local time, for tables. */
export function formatIsoDate(iso: string | null | undefined): string | null {
  const d = parseDate(iso)
  if (!d) return null
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/** ISO date and time (YYYY-MM-DD HH:MM) in local time. */
export function formatIsoDateTime(iso: string | null | undefined): string | null {
  const d = parseDate(iso)
  if (!d) return null
  return `${formatIsoDate(iso)} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** Extended Italian date for running text: "2 agosto 2026". */
export function formatLongDate(iso: string | null | undefined): string | null {
  const d = parseDate(iso)
  if (!d) return null
  return longDateFormatter.format(d)
}
