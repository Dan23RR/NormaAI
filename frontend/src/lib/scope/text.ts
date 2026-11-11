/**
 * Labels and the plain-text export of an assessment ("Copia il risultato").
 * The words live in the `ambito.results`, `ambito.summary` and
 * `ambito.text` messages; this module only puts them together.
 */
import type { BadgeTone } from '@/components/ui/Badge'
import { formatEur, formatInt } from '@/i18n/format'
import type { TextContext, Translate } from '@/i18n/types'
import { latestVerifiedOn } from '@/lib/verification'
import { dateWithArticle, sourceLine } from './sources'
import type { ScopeAssessment, ScopeFramework, ScopeInput, ScopeResult, ScopeStatus } from './types'

export const STATUS_TONE: Record<ScopeStatus, BadgeTone> = {
  in_scope: 'union',
  out_of_scope: 'neutral',
  conditional: 'warn',
  not_assessed: 'neutral',
}

/** What applies comes first when the results are read top to bottom. */
const STATUS_ORDER: Record<ScopeStatus, number> = { in_scope: 0, conditional: 1, out_of_scope: 2, not_assessed: 3 }

/** The results with what applies first, then what depends; the order of the rule sets is kept within a status. */
export function byRelevance(results: ScopeResult[]): ScopeResult[] {
  return results
    .map((result, index) => ({ result, index }))
    .sort((a, b) => STATUS_ORDER[a.result.status] - STATUS_ORDER[b.result.status] || a.index - b.index)
    .map((entry) => entry.result)
}

export function statusLabel(status: ScopeStatus, t: Translate): string {
  return t(`ambito.results.status.${status}`)
}

export function frameworkTitle(framework: ScopeFramework, t: Translate): string {
  return t(`ambito.results.frameworks.${framework}`)
}

/** Short name of a rule set for its badge: "AI Act", "IA e lavoro", "Macchine". */
export function frameworkBadge(framework: ScopeFramework, t: Translate): string {
  return t(`ambito.results.badges.${framework}`)
}

/** "Acme Srl: 1.500 dipendenti, ricavi netti 620.000.000 €, non quotata, società singola, IT" */
export function inputSummary(input: ScopeInput, ctx: TextContext): string {
  const { t, locale } = ctx
  const parts: string[] = []
  if (input.employees != null) parts.push(t('ambito.summary.employees', { count: formatInt(input.employees, locale) }))
  if (input.turnoverEur != null) parts.push(t('ambito.summary.turnover', { amount: formatEur(input.turnoverEur, locale) }))
  if (input.balanceSheetEur != null) {
    parts.push(t('ambito.summary.balanceSheet', { amount: formatEur(input.balanceSheetEur, locale) }))
  }
  if (input.nonEu) {
    parts.push(t('ambito.summary.nonEu'))
    if (input.euTurnoverEur != null) parts.push(t('ambito.summary.euTurnover', { amount: formatEur(input.euTurnoverEur, locale) }))
  }
  parts.push(t(input.listedEu ? 'ambito.summary.listed' : 'ambito.summary.notListed'))
  if (input.wave1Reporter) parts.push(t('ambito.summary.wave1'))
  parts.push(t(`ambito.summary.groupRoles.${input.groupRole}`))
  if (input.nis && input.nis.sector !== 'nessuno') {
    parts.push(t('ambito.summary.nisSector', { sector: t(`ambito.nis.sectors.${input.nis.sector}`) }))
  }
  if (input.sector?.trim()) parts.push(input.sector.trim())
  if (input.country) parts.push(input.country)
  const name = input.name?.trim()
  return name ? `${name}: ${parts.join(', ')}` : parts.join(', ')
}

function resultToText(r: ScopeResult, ctx: TextContext): string {
  const { t } = ctx
  const lines: string[] = []
  const from = r.fromLabel ? ` (${r.fromLabel.charAt(0).toLowerCase()}${r.fromLabel.slice(1)})` : ''
  lines.push(`${frameworkTitle(r.framework, t)}: ${statusLabel(r.status, t)}${from}`)
  lines.push(r.headline)
  for (const reason of r.reasons) lines.push(`- ${reason}`)
  if (r.obligations?.length) {
    for (const o of r.obligations) {
      const exception = o.exception ? ` ${o.exception}` : ''
      lines.push(`- ${o.whoLabel}: ${o.title} (${o.article}). ${o.requirement}${exception}`)
    }
  }
  if (r.notes.length) {
    lines.push(t('ambito.text.notes'))
    for (const note of r.notes) lines.push(`- ${note}`)
  }
  lines.push(t('ambito.text.sources'))
  for (const s of r.sources) {
    lines.push(`[${s.index}] ${sourceLine(s, ctx)}`)
    if (s.quote) lines.push(`    ${t('ambito.text.passage', { text: s.quote })}`)
  }
  return lines.join('\n')
}

/** ISO date of the most recent check among the sources an assessment cites. */
export function assessmentCheckedOn(a: ScopeAssessment): string | undefined {
  return latestVerifiedOn(a.results.flatMap((r) => r.sources.map((s) => s.id)))
}

export function assessmentToText(a: ScopeAssessment, ctx: TextContext): string {
  const { t } = ctx
  const checkedOn = assessmentCheckedOn(a)
  const header = [
    checkedOn ? t('ambito.text.header', { date: dateWithArticle(checkedOn, ctx) }) : t('ambito.text.headerUnchecked'),
    t('ambito.text.profile', { summary: inputSummary(a.input, ctx) }),
    t('ambito.text.disclaimer'),
  ]
  return [header.join('\n'), ...byRelevance(a.results).map((r) => resultToText(r, ctx))].join('\n\n')
}
