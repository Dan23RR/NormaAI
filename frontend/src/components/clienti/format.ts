/**
 * Formatting for the application: thousands separators of the interface
 * language, ISO dates in tables, extended dates in running text (DESIGN.md,
 * principle 2). Components that render numbers directly use `useFormatter`.
 */
import type { Locale } from '@/i18n/config'
import { formatEur as formatEurValue, formatInt as formatIntValue } from '@/i18n/format'

export function formatInt(value: number | null | undefined, locale: Locale): string | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  return formatIntValue(value, locale)
}

export function formatEur(value: number | null | undefined, locale: Locale): string | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  return formatEurValue(value, locale)
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
