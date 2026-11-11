/**
 * Dated obligations and milestones for the Monitoraggio calendar.
 *
 * Curated by hand, one provision per date: `source` is the id, in the
 * registry of src/lib/verification, of the provision whose official text
 * carries the date; `related` are the provisions the description of the
 * entry relies on. Whether and when each one was found in the official text
 * comes from scripts/verify_site_sources.py: an entry whose source that
 * check did not verify is not shown. The title, who and what of each entry
 * live in the `monitoraggio.calendar` messages.
 */
import type { TextContext } from '@/i18n/types'
import { scopeSource, scopeSources, type ScopeSource } from '@/lib/scope/sources'
import { addDays, parseIsoDate, startOfDay, toIsoDate, type DatePrecision } from './dates'

export interface ObligationData {
  id: string
  /** ISO date. */
  date: string
  precision: DatePrecision
  /** Key of the badge: CSRD, CSDDD, AI_ACT, AI_WORK, NIS2, DORA, CRA, MACHINERY, EUDR, PAY. */
  framework: string
  /** Registry id of the provision that carries the date. */
  source: string
  /** Registry ids of the provisions the description relies on. */
  related: string[]
}

export interface Obligation extends Omit<ObligationData, 'source' | 'related'> {
  title: string
  /** Who the entry applies to. */
  who: string
  /** What to do. */
  what: string
  source: ScopeSource
  related: ScopeSource[]
  /** ISO date of the check that found the provision in the official text; undefined when not verified. */
  verifiedOn?: string
}

function entry(id: string, date: string, framework: string, source: string, related: string[] = []): ObligationData {
  return { id, date, precision: 'day', framework, source, related }
}

export const OBLIGATION_DATA: ObligationData[] = [
  entry('nis2-application', '2024-10-18', 'NIS2', 'nis2-dir-41-1', ['nis2-dir-2-1']),
  entry('dora-application', '2025-01-17', 'DORA', 'dora-64', ['dora-2-1']),
  entry('aiact-art4-art5', '2025-02-02', 'AI_ACT', 'ai-act-113-a', ['ai-act-4-1', 'ai-act-5-1-f']),
  entry('aiact-gpai', '2025-08-02', 'AI_ACT', 'ai-act-113-b', ['ai-act-53-1']),
  entry('aiact-art50', '2026-08-02', 'AI_ACT', 'ai-act-113-general', ['ai-act-50-1', 'ai-act-50-2', 'ai-act-50-4']),
  entry('cra-reporting', '2026-09-11', 'CRA', 'cra-71-2', ['cra-14-1', 'cra-14-2']),
  entry('ai-work-decree', '2026-10-23', 'AI_WORK', 'dlgs-179-2026-41-1', ['dlgs-179-2026-41-3', 'dlgs-179-2026-42-2']),
  entry('aiact-legacy-marking', '2026-12-02', 'AI_ACT', 'ai-act-111-4', ['ai-act-50-2']),
  entry('aiact-new-prohibitions', '2026-12-02', 'AI_ACT', 'ai-act-113-a', ['ai-act-5-1-bbis', 'ai-act-5-1-bter']),
  entry('eudr-application', '2026-12-30', 'EUDR', 'eudr-38-2', ['eudr-1-1']),
  entry('csrd-first-year', '2027-01-01', 'CSRD', 'csrd-5-2-b', ['dlgs-125-2024-17-1-b', 'dlgs-125-2024-17-3bis']),
  entry('nis2-incidents-2026', '2027-01-01', 'NIS2', 'acn-det-127434-2026-1-2', ['dlgs-138-2024-25-5']),
  entry('machinery-application', '2027-01-20', 'MACHINERY', 'mach-54', ['mach-52-1']),
  entry('nis2-registration', '2027-02-28', 'NIS2', 'dlgs-138-2024-7-1'),
  entry('omnibus-transposition', '2027-03-19', 'CSRD', 'omnibus-5-1', ['dir-2013-34-19bis-1']),
  entry('nis2-annual-update', '2027-05-31', 'NIS2', 'dlgs-138-2024-7-4', ['dlgs-138-2024-7-3']),
  entry('pay-gap-first-data', '2027-06-07', 'PAY', 'dlgs-96-2026-9-9', ['dlgs-96-2026-9-1', 'dlgs-96-2026-9-5', 'dlgs-96-2026-9-8']),
  entry('eudr-small-operators', '2027-06-30', 'EUDR', 'eudr-38-3', ['eudr-38-2']),
  entry('csddd-guidelines', '2027-07-26', 'CSDDD', 'csddd-19-3'),
  entry('nis2-measures-2026', '2027-07-31', 'NIS2', 'acn-det-127434-2026-1-1', ['dlgs-138-2024-24-1']),
  entry('aiact-gpai-legacy', '2027-08-02', 'AI_ACT', 'ai-act-111-3'),
  entry('aiact-high-risk-annex-iii', '2027-12-02', 'AI_ACT', 'ai-act-113-c-i', ['ai-act-26-7']),
  entry('cra-full-application', '2027-12-11', 'CRA', 'cra-71-2', ['cra-2-1']),
  entry('csddd-transposition', '2028-07-26', 'CSDDD', 'csddd-37-1-recepimento'),
  entry('aiact-high-risk-annex-i', '2028-08-02', 'AI_ACT', 'ai-act-113-c-ii'),
  entry('csddd-first-compliance', '2029-07-26', 'CSDDD', 'csddd-37-1-applicazione', ['csddd-2-1-a']),
]

/** Every registry id the calendar cites. */
export const CALENDAR_SOURCE_IDS: string[] = Array.from(new Set(OBLIGATION_DATA.flatMap((o) => [o.source, ...o.related])))

/** The calendar in the words of the interface, every entry with what the last check found. */
export function obligations(ctx: TextContext): Obligation[] {
  return OBLIGATION_DATA.map(({ source, related, ...data }) => {
    const primary = scopeSource(source, ctx)
    return {
      ...data,
      title: ctx.t(`monitoraggio.calendar.${data.id}.title`),
      who: ctx.t(`monitoraggio.calendar.${data.id}.who`),
      what: ctx.t(`monitoraggio.calendar.${data.id}.what`),
      source: primary,
      related: scopeSources(related, ctx),
      verifiedOn: primary.status === 'verified' ? primary.verifiedAt : undefined,
    }
  })
}

/** Only the entries whose date was found in the official text: the ones the calendar shows. */
export function verifiedOnly(list: Obligation[]): Obligation[] {
  return list.filter((o) => o.verifiedOn != null)
}

function byDate(a: Obligation, b: Obligation): number {
  return a.date < b.date ? -1 : a.date > b.date ? 1 : a.id.localeCompare(b.id)
}

/** Entries dated within [from, from + days], ascending. */
export function upcoming(from: Date, days: number, list: Obligation[]): Obligation[] {
  const start = toIsoDate(startOfDay(from))
  const end = toIsoDate(addDays(startOfDay(from), days))
  return list.filter((o) => o.date >= start && o.date <= end).sort(byDate)
}

/** Entries dated before `from`, most recent first. */
export function past(from: Date, list: Obligation[]): Obligation[] {
  const start = toIsoDate(startOfDay(from))
  return list.filter((o) => o.date < start).sort((a, b) => byDate(b, a))
}

export interface MonthGroup {
  /** 'YYYY-MM' */
  key: string
  /** ISO date of the first day, for formatting the heading. */
  firstDay: string
  items: Obligation[]
}

export function groupByMonth(list: Obligation[]): MonthGroup[] {
  const groups = new Map<string, MonthGroup>()
  for (const o of [...list].sort(byDate)) {
    const key = o.date.slice(0, 7)
    const group = groups.get(key) ?? { key, firstDay: `${key}-01`, items: [] }
    group.items.push(o)
    groups.set(key, group)
  }
  return Array.from(groups.values())
}

export function isPast(o: Obligation, today: Date): boolean {
  return parseIsoDate(o.date) < startOfDay(today)
}
