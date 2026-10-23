/**
 * Date helpers shared by the obligations calendar and the scope engine.
 * Dates travel as ISO 'YYYY-MM-DD' strings and are parsed in local time, so
 * a deadline never shifts by a day across time zones. Formatting for the
 * reader lives in src/i18n/format.ts (and useDateFormat for components).
 */

export type { DatePrecision } from '@/i18n/format'

export function parseIsoDate(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, (m || 1) - 1, d || 1)
}

export function toIsoDate(date: Date): string {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

export function startOfDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate())
}

export function addDays(date: Date, days: number): Date {
  const next = new Date(date)
  next.setDate(next.getDate() + days)
  return next
}
