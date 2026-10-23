/**
 * Dated obligations and milestones for the Monitoraggio calendar.
 *
 * Curated by hand. Every date comes from a file of this repository and the
 * entry says which one (`sourceNote`). Dates the sources give only by month
 * or quarter keep that precision; entries the sources present as expected
 * rather than fixed carry `confirmed: false` and the interface says so.
 * No automatic EUR-Lex watcher feeds this list yet. The title, who and
 * what of each entry live in the `monitoraggio.calendar` messages.
 */
import type { TextContext } from '@/i18n/types'
import type { Source } from '@/lib/sources'
import { VERIFIED_ON, scopeSources, type ScopeSourceKey } from '@/lib/scope/sources'
import { addDays, parseIsoDate, startOfDay, toIsoDate, type DatePrecision } from './dates'

export interface ObligationData {
  id: string
  /** ISO date. Month precision uses day 01; quarter precision uses the first day of the quarter. */
  date: string
  precision: DatePrecision
  /** Key of FRAMEWORK_META (CSRD, CSDDD, AI_ACT, CRA, NIS2, DORA, ...). */
  framework: string
  source: ScopeSourceKey
  /** Where in the repository the date was read (provenance, kept as written). */
  sourceNote: string
  /** False when the sources present the date as expected, not fixed. */
  confirmed: boolean
  verifiedOn: string
}

export interface Obligation extends Omit<ObligationData, 'source'> {
  title: string
  /** Who the entry applies to. */
  who: string
  /** What to do. */
  what: string
  source: Source
}

type Draft = Omit<ObligationData, 'verifiedOn' | 'confirmed' | 'precision'> & {
  precision?: DatePrecision
  confirmed?: boolean
}

function entry(d: Draft): ObligationData {
  return { precision: 'day', confirmed: true, verifiedOn: VERIFIED_ON, ...d }
}

export const OBLIGATION_DATA: ObligationData[] = [
  entry({
    id: 'nis2-application',
    date: '2024-10-18',
    framework: 'NIS2',
    source: 'nis2',
    sourceNote: 'Codex, cap. 5.1 e note (CELEX 32022L2555); landing, tabella Fonti',
  }),
  entry({
    id: 'dora-application',
    date: '2025-01-17',
    framework: 'DORA',
    source: 'dora',
    sourceNote: 'Codex, cap. 5.1 e note (CELEX 32022R2554); landing, tabella Fonti',
  }),
  entry({
    id: 'aiact-art4-art5',
    date: '2025-02-02',
    framework: 'AI_ACT',
    source: 'aiAct5',
    sourceNote: 'public/scope-aiact.html, note del verdetto',
  }),
  entry({
    id: 'aiact-gpai',
    date: '2025-08-02',
    framework: 'AI_ACT',
    source: 'aiActGpai',
    sourceNote: 'public/scope-aiact.html, note del verdetto',
  }),
  entry({
    id: 'omnibus-published',
    date: '2026-02-26',
    framework: 'CSRD',
    source: 'omnibusI',
    sourceNote: 'README.md, Regulatory Context; .planning/decisions/003',
  }),
  entry({
    id: 'omnibus-in-force',
    date: '2026-03-18',
    framework: 'CSRD',
    source: 'omnibusI',
    sourceNote: 'public/scope-csrd.html; prompts/gap_analyst.txt riga 45; README.md',
  }),
  entry({
    id: 'aiact-code-of-practice',
    date: '2026-06-10',
    framework: 'AI_ACT',
    source: 'aiAct50_2',
    sourceNote: 'public/scope-aiact.html, obbligo "gen"',
  }),
  entry({
    id: 'aiact-art50',
    date: '2026-08-02',
    framework: 'AI_ACT',
    source: 'aiAct113',
    sourceNote: 'public/scope-aiact.html; src/app/page.tsx (esempio di risposta); Codex, cap. 5.2',
  }),
  entry({
    id: 'cra-reporting',
    date: '2026-09-11',
    framework: 'CRA',
    source: 'cra',
    sourceNote: 'prompts/gap_analyst.txt riga 47; .planning/decisions/004',
  }),
  entry({
    id: 'aiact-legacy-marking',
    date: '2026-12-02',
    framework: 'AI_ACT',
    source: 'aiAct50_2',
    sourceNote: 'public/scope-aiact.html, obbligo "gen"',
  }),
  entry({
    id: 'csrd-prepare-fy2027',
    date: '2026-12-31',
    framework: 'CSRD',
    source: 'codex',
    sourceNote: 'Codex, cap. 5.2 (2026, Q3)',
  }),
  entry({
    id: 'csrd-first-post-omnibus',
    date: '2027-01-01',
    precision: 'quarter',
    framework: 'CSRD',
    source: 'codex',
    sourceNote: 'Codex, cap. 5.1 e 5.2 (2027, Q1)',
    confirmed: false,
  }),
  entry({
    id: 'csrd-csddd-review-clause',
    date: '2027-04-01',
    precision: 'quarter',
    framework: 'CSRD',
    source: 'codex',
    sourceNote: 'Codex, cap. 1.2 e 5.2 (2027, Q2)',
    confirmed: false,
  }),
  entry({
    id: 'csddd-guidelines',
    date: '2027-07-01',
    precision: 'month',
    framework: 'CSDDD',
    source: 'csddd',
    sourceNote: '.planning/decisions/003 (verifica 2026-06-11)',
    confirmed: false,
  }),
  entry({
    id: 'aiact-high-risk-annex-iii',
    date: '2027-12-02',
    framework: 'AI_ACT',
    source: 'aiActHighRisk',
    sourceNote: 'public/scope-aiact.html (quadro aggiornato al 12 luglio 2026)',
  }),
  entry({
    id: 'cra-full-application',
    date: '2027-12-11',
    framework: 'CRA',
    source: 'cra',
    sourceNote: 'prompts/gap_analyst.txt riga 47; .planning/decisions/004',
  }),
  entry({
    id: 'csrd-wave1-fy2027',
    date: '2028-04-01',
    precision: 'quarter',
    framework: 'CSRD',
    source: 'codex',
    sourceNote: 'Codex, cap. 5.2 (2028, Q2)',
  }),
  entry({
    id: 'csddd-transposition',
    date: '2028-07-26',
    framework: 'CSDDD',
    source: 'csddd',
    sourceNote: 'public/scope-csrd.html; Codex, cap. 1.4 e 5; prompts/gap_analyst.txt riga 46; .planning/decisions/003; landing, tabella Fonti',
  }),
  entry({
    id: 'aiact-high-risk-annex-i',
    date: '2028-08-02',
    framework: 'AI_ACT',
    source: 'aiActHighRisk',
    sourceNote: 'public/scope-aiact.html (quadro aggiornato al 12 luglio 2026)',
  }),
  entry({
    id: 'csddd-first-compliance',
    date: '2029-07-26',
    framework: 'CSDDD',
    source: 'csddd',
    sourceNote: 'prompts/gap_analyst.txt riga 46; .planning/decisions/003; Codex, cap. 2.2 e 5.2',
  }),
]

/** The calendar in the words of the interface. */
export function obligations(ctx: TextContext): Obligation[] {
  const sources = scopeSources(ctx)
  return OBLIGATION_DATA.map(({ source, ...data }) => ({
    ...data,
    title: ctx.t(`monitoraggio.calendar.${data.id}.title`),
    who: ctx.t(`monitoraggio.calendar.${data.id}.who`),
    what: ctx.t(`monitoraggio.calendar.${data.id}.what`),
    source: sources[source],
  }))
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
