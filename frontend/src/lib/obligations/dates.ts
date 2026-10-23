/**
 * Date helpers shared by the obligations calendar and the scope engine.
 * Dates travel as ISO 'YYYY-MM-DD' strings and are parsed in local time, so
 * a deadline never shifts by a day across time zones.
 */

export type DatePrecision = 'day' | 'month' | 'quarter'

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

const longDate = new Intl.DateTimeFormat('it-IT', { day: 'numeric', month: 'long', year: 'numeric' })
const monthYear = new Intl.DateTimeFormat('it-IT', { month: 'long', year: 'numeric' })
const QUARTERS = ['primo', 'secondo', 'terzo', 'quarto']

/** "2 agosto 2026", "luglio 2029" or "primo trimestre 2027" depending on precision. */
export function formatDateIt(iso: string, precision: DatePrecision = 'day'): string {
  const date = parseIsoDate(iso)
  if (precision === 'day') return longDate.format(date)
  if (precision === 'month') return monthYear.format(date)
  return `${QUARTERS[Math.floor(date.getMonth() / 3)]} trimestre ${date.getFullYear()}`
}

export function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/** "Dicembre 2026": the heading of a month group. */
export function formatMonthHeading(iso: string): string {
  return capitalize(monthYear.format(parseIsoDate(iso)))
}
