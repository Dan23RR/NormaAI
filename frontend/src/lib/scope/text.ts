/**
 * Labels and the plain-text export of an assessment ("Copia il risultato").
 * The words live in the `ambito.results`, `ambito.summary` and
 * `ambito.text` messages; this module only puts them together.
 */
import type { BadgeTone } from '@/components/ui/Badge'
import { formatDate, formatEur, formatInt } from '@/i18n/format'
import type { TextContext, Translate } from '@/i18n/types'
import { sourceLine } from './sources'
import type { ScopeAssessment, ScopeFramework, ScopeInput, ScopeResult, ScopeStatus } from './types'

export const STATUS_TONE: Record<ScopeStatus, BadgeTone> = {
  in_scope: 'union',
  out_of_scope: 'neutral',
  conditional: 'warn',
  not_assessed: 'neutral',
}

export function statusLabel(status: ScopeStatus, t: Translate): string {
  return t(`ambito.results.status.${status}`)
}

export function frameworkTitle(framework: ScopeFramework, t: Translate): string {
  return t(`ambito.results.frameworks.${framework}`)
}

/** "Acme Srl: 1.500 dipendenti, ricavi netti 620.000.000 €, non quotata, società singola, IT" */
export function inputSummary(input: ScopeInput, ctx: TextContext): string {
  const { t, locale } = ctx
  const parts: string[] = []
  if (input.employees != null) parts.push(t('ambito.summary.employees', { count: formatInt(input.employees, locale) }))
  if (input.turnoverEur != null) parts.push(t('ambito.summary.turnover', { amount: formatEur(input.turnoverEur, locale) }))
  if (input.nonEu) {
    parts.push(t('ambito.summary.nonEu'))
    if (input.euTurnoverEur != null) parts.push(t('ambito.summary.euTurnover', { amount: formatEur(input.euTurnoverEur, locale) }))
  }
  parts.push(t(input.listedEu ? 'ambito.summary.listed' : 'ambito.summary.notListed'))
  if (input.wave1Reporter) parts.push(t('ambito.summary.wave1'))
  parts.push(t(`ambito.summary.groupRoles.${input.groupRole}`))
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
      lines.push(`- ${o.whoLabel}: ${o.title} (${o.article}). ${o.requirement}`)
    }
  }
  if (r.notes.length) {
    lines.push(t('ambito.text.notes'))
    for (const note of r.notes) lines.push(`- ${note}`)
  }
  if (r.passages.length) {
    for (const p of r.passages) {
      lines.push(
        t('ambito.text.passage', {
          text: [p.before, p.quote, p.after].filter(Boolean).join(' '),
          act: p.act,
          article: p.article,
        }),
      )
    }
  }
  lines.push(t('ambito.text.sources'))
  for (const s of r.sources) lines.push(`[${s.index}] ${sourceLine(s)}`)
  return lines.join('\n')
}

export function assessmentToText(a: ScopeAssessment, ctx: TextContext): string {
  const { t } = ctx
  const header = [
    t('ambito.text.header', { date: formatDate(a.verifiedOn, ctx) }),
    t('ambito.text.profile', { summary: inputSummary(a.input, ctx) }),
    t('ambito.text.disclaimer'),
  ]
  return [header.join('\n'), ...a.results.map((r) => resultToText(r, ctx))].join('\n\n')
}
