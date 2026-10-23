/**
 * Dates and numbers for the libraries that build text outside React
 * (scope rules, obligations calendar, clipboard). Components format with
 * `useFormatter` from next-intl; both go through the same Intl data, so
 * the output is identical: "2 agosto 2026" / "2 August 2026", "1.200" / "1,200".
 */
import type { DateTimeFormatOptions, NumberFormatOptions } from 'next-intl'
import type { Locale } from './config'
import type { TextContext } from './types'

export type DatePrecision = 'day' | 'month' | 'quarter'

// Typed with next-intl's option types (a subset of Intl's), so the same
// constants serve `useFormatter` in components and `Intl` here.
export const LONG_DATE: DateTimeFormatOptions = { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' }
export const MONTH_YEAR: DateTimeFormatOptions = { month: 'long', year: 'numeric', timeZone: 'UTC' }
export const INT: NumberFormatOptions = { maximumFractionDigits: 0, useGrouping: 'always' }
export const EUR: NumberFormatOptions = { style: 'currency', currency: 'EUR', maximumFractionDigits: 0, useGrouping: 'always' }

/** "YYYY-MM-DD" (or a timestamp starting with it) as a UTC date, so the day never shifts with the time zone. */
export function isoToUtcDate(iso: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso.trim())
  if (!m) return null
  const date = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])))
  return Number.isNaN(date.getTime()) ? null : date
}

export function quarterOf(date: Date): number {
  return Math.floor(date.getUTCMonth() / 3) + 1
}

/** "2 agosto 2026", "luglio 2029" or "primo trimestre 2027" depending on precision. */
export function formatDate(iso: string, ctx: TextContext, precision: DatePrecision = 'day'): string {
  const date = isoToUtcDate(iso)
  if (!date) return iso
  if (precision === 'day') return new Intl.DateTimeFormat(ctx.locale, LONG_DATE).format(date)
  if (precision === 'month') return new Intl.DateTimeFormat(ctx.locale, MONTH_YEAR).format(date)
  // Strings on purpose: a number argument would be grouped ("2,027").
  return ctx.t('ui.dates.quarter', { quarter: String(quarterOf(date)), year: String(date.getUTCFullYear()) })
}

/** "Dicembre 2026" / "December 2026": the heading of a month group. */
export function formatMonthHeading(iso: string, locale: Locale): string {
  const date = isoToUtcDate(iso)
  if (!date) return iso
  const text = new Intl.DateTimeFormat(locale, MONTH_YEAR).format(date)
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/**
 * The corpus date as the answer shows it. A value that is not a date comes
 * back as it is: the page never invents a date, but does not hide what the
 * backend sent either.
 */
export function formatCorpusDate(value: string | null | undefined, locale: Locale): string | undefined {
  if (typeof value !== 'string') return undefined
  const trimmed = value.trim()
  if (!trimmed) return undefined
  const date = isoToUtcDate(trimmed)
  if (!date) return trimmed
  try {
    return new Intl.DateTimeFormat(locale, LONG_DATE).format(date)
  } catch {
    return trimmed
  }
}

/** "1.200" / "1,200": thousands grouped also on four digits (Italian CLDR data would write "1200"). */
export function formatInt(n: number, locale: Locale): string {
  return new Intl.NumberFormat(locale, INT).format(n)
}

/** "450.000.000 €" / "€450,000,000" */
export function formatEur(n: number, locale: Locale): string {
  return new Intl.NumberFormat(locale, EUR).format(n)
}

/** "450 milioni di euro", "1,5 miliardi di euro" / "450 million euro", "1.5 billion euro". */
export function formatMillionsEur(n: number, ctx: TextContext): string {
  if (n >= 1_000_000_000) {
    const value = Math.round((n / 1_000_000_000) * 10) / 10
    return ctx.t('ui.amounts.billionsEur', { value })
  }
  const value = Math.round((n / 1_000_000) * 10) / 10
  return ctx.t('ui.amounts.millionsEur', { value })
}

/**
 * A number typed in the conventions of the locale: "1.200", "450.000.000"
 * and "1,5" in Italian; "1,200", "450,000,000" and "1.5" in English. Plain
 * digits, spaces and euro signs are accepted in both.
 */
export function parseNumber(raw: string | number | null | undefined, locale: Locale): number | null {
  if (raw == null) return null
  if (typeof raw === 'number') return Number.isFinite(raw) ? raw : null
  let s = String(raw).trim().replace(/\s/g, '').replace(/€/g, '')
  if (s === '') return null
  const group = locale.startsWith('en') ? ',' : '.'
  const decimal = group === ',' ? '.' : ','
  const groupRe = new RegExp(`\\${group}`, 'g')
  if (s.includes(decimal)) {
    s = s.replace(groupRe, '').replace(decimal, '.')
  } else if (new RegExp(`^\\d{1,3}(\\${group}\\d{3})+$`).test(s)) {
    s = s.replace(groupRe, '')
  } else if (group === '.' && /^\d+\.\d{1,2}$/.test(s)) {
    // decimal point kept: "12.5"
  } else {
    s = s.replace(groupRe, '')
  }
  const n = parseFloat(s.replace(/[^0-9.]/g, ''))
  return Number.isFinite(n) ? n : null
}
