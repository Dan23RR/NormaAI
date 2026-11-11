/**
 * Where a company profile stands against the size thresholds the demo
 * scenarios depend on. Thresholds as read on the official texts on
 * 2026-11-11:
 *
 * - CSRD (and the Taxonomy disclosure that follows it): net turnover above
 *   EUR 450 000 000 AND more than 1 000 employees on average, Art. 19a(1) of
 *   Directive 2013/34/EU as amended by Directive (EU) 2026/470;
 * - CSDDD: more than 5 000 employees AND net worldwide turnover above
 *   EUR 1 500 000 000, Art. 2(1)(a) of Directive (EU) 2024/1760 as amended;
 * - NIS2: entities of the annexes that exceed the ceilings for small
 *   enterprises (fewer than 50 persons and turnover or balance sheet total
 *   not above EUR 10 million), Art. 3(2) of Legislative Decree 138/2024 and
 *   Art. 2(2) of the Annex to Recommendation 2003/361/EC. The demo has no
 *   balance sheet total, so it reads the ceiling on turnover alone.
 */
import { LOCALES, type Language } from '@/i18n/config'
import type { DemoProfile } from './types'

export const CSRD_EMPLOYEES = 1_000
export const CSRD_TURNOVER_EUR = 450_000_000
export const CSDDD_EMPLOYEES = 5_000
export const CSDDD_TURNOVER_EUR = 1_500_000_000
export const SMALL_ENTERPRISE_PERSONS = 50
export const SMALL_ENTERPRISE_TURNOVER_EUR = 10_000_000

/** `above`: over every threshold; `below`: under at least one; `unknown`: no size in the profile. */
export type Scope = 'above' | 'below' | 'unknown'

function sizeOf(profile: DemoProfile | undefined): { employees: number; revenue: number } | null {
  const employees = profile?.employee_count
  const revenue = profile?.revenue_eur
  if (typeof employees !== 'number' || typeof revenue !== 'number') return null
  // A profile left empty (0 employees and no turnover) says nothing about size.
  if (employees <= 0 && revenue <= 0) return null
  return { employees, revenue }
}

export function csrdScope(profile: DemoProfile | undefined): Scope {
  const size = sizeOf(profile)
  if (!size) return 'unknown'
  return size.employees > CSRD_EMPLOYEES && size.revenue > CSRD_TURNOVER_EUR ? 'above' : 'below'
}

export function csdddScope(profile: DemoProfile | undefined): Scope {
  const size = sizeOf(profile)
  if (!size) return 'unknown'
  return size.employees > CSDDD_EMPLOYEES && size.revenue > CSDDD_TURNOVER_EUR ? 'above' : 'below'
}

/** `below` means a small enterprise: as a rule outside NIS2, whatever the sector. */
export function nis2Scope(profile: DemoProfile | undefined): Scope {
  const size = sizeOf(profile)
  if (!size) return 'unknown'
  return size.employees < SMALL_ENTERPRISE_PERSONS && size.revenue <= SMALL_ENTERPRISE_TURNOVER_EUR ? 'below' : 'above'
}

const FINANCIAL_SECTOR = /\b(banc|bank|assicura|insur|finanz|financ|credito|credit|pagament|payment|sgr|sim\b|invest)/i

/** DORA applies to financial entities (Art. 2): read from the sector the consultant typed. */
export function doraScope(profile: DemoProfile | undefined): Scope {
  const sector = profile?.sector?.trim()
  if (!sector) return 'unknown'
  return FINANCIAL_SECTOR.test(sector) ? 'above' : 'below'
}

/** "85" / "1.650" (Italian) or "1,650" (English). */
export function formatEmployees(n: number, language: Language): string {
  return new Intl.NumberFormat(LOCALES[language], { maximumFractionDigits: 0, useGrouping: 'always' }).format(n)
}

/** "14 milioni di euro", "1,5 miliardi di euro" / "EUR 14 million", "EUR 1.5 billion". */
export function formatTurnover(eur: number, language: Language): string {
  const billions = eur >= 1_000_000_000
  const value = new Intl.NumberFormat(LOCALES[language], { maximumFractionDigits: 1 }).format(
    eur / (billions ? 1_000_000_000 : 1_000_000),
  )
  if (language === 'en') return `EUR ${value} ${billions ? 'billion' : 'million'}`
  return `${value} ${billions ? 'miliardi' : 'milioni'} di euro`
}

/** "con 85 dipendenti e 14 milioni di euro di ricavi netti" / "with 85 employees and a net turnover of EUR 14 million". */
export function describeSize(profile: DemoProfile | undefined, language: Language): string {
  const size = sizeOf(profile)
  if (!size) return ''
  const employees = formatEmployees(size.employees, language)
  const turnover = formatTurnover(size.revenue, language)
  return language === 'en'
    ? `with ${employees} employees and a net turnover of ${turnover}`
    : `con ${employees} dipendenti e ${turnover} di ricavi netti`
}

/** The name to use in a sentence, or a neutral subject when the profile has none. */
export function companyName(profile: DemoProfile | undefined, language: Language): string {
  const name = profile?.name?.trim()
  if (name) return name
  return language === 'en' ? 'The company' : "L'impresa"
}
