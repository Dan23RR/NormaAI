/**
 * Labels and the plain-text export of an assessment ("Copia il risultato").
 */
import type { BadgeTone } from '@/components/ui/Badge'
import { formatDateIt } from '@/lib/obligations/dates'
import { formatEur, formatInt } from './format'
import { sourceLine } from './sources'
import type { ScopeAssessment, ScopeFramework, ScopeInput, ScopeResult, ScopeStatus } from './types'

export const STATUS_META: Record<ScopeStatus, { label: string; tone: BadgeTone }> = {
  in_scope: { label: 'Si applica', tone: 'union' },
  out_of_scope: { label: 'Non si applica', tone: 'neutral' },
  conditional: { label: 'Dipende', tone: 'warn' },
  not_assessed: { label: 'Non valutato', tone: 'neutral' },
}

export const FRAMEWORK_TITLE: Record<ScopeFramework, string> = {
  CSRD: 'CSRD, rendicontazione di sostenibilità',
  CSDDD: 'CSDDD, dovere di diligenza',
  AI_ACT: 'AI Act, trasparenza (art. 50)',
}

export const GROUP_ROLE_LABEL: Record<ScopeInput['groupRole'], string> = {
  standalone: 'società singola',
  parent: 'capogruppo con bilancio consolidato',
  subsidiary: 'società controllata',
}

/** "Acme Srl: 1.500 dipendenti, ricavi netti 620.000.000 €, non quotata, società singola, IT" */
export function inputSummary(input: ScopeInput): string {
  const parts: string[] = []
  if (input.employees != null) parts.push(`${formatInt(input.employees)} dipendenti`)
  if (input.turnoverEur != null) parts.push(`ricavi netti ${formatEur(input.turnoverEur)}`)
  if (input.nonEu) {
    parts.push('sede fuori dall’UE')
    if (input.euTurnoverEur != null) parts.push(`ricavi netti nell’UE ${formatEur(input.euTurnoverEur)}`)
  }
  parts.push(input.listedEu ? 'quotata in un mercato regolamentato UE' : 'non quotata')
  if (input.wave1Reporter) parts.push('già in rendicontazione (Wave 1)')
  parts.push(GROUP_ROLE_LABEL[input.groupRole])
  if (input.sector?.trim()) parts.push(input.sector.trim())
  if (input.country) parts.push(input.country)
  const name = input.name?.trim()
  return name ? `${name}: ${parts.join(', ')}` : parts.join(', ')
}

function resultToText(r: ScopeResult): string {
  const lines: string[] = []
  const from = r.fromLabel ? ` (${r.fromLabel.charAt(0).toLowerCase()}${r.fromLabel.slice(1)})` : ''
  lines.push(`${FRAMEWORK_TITLE[r.framework]}: ${STATUS_META[r.status].label}${from}`)
  lines.push(r.headline)
  for (const reason of r.reasons) lines.push(`- ${reason}`)
  if (r.obligations?.length) {
    for (const o of r.obligations) {
      lines.push(`- ${o.whoLabel}: ${o.title} (${o.article}). ${o.requirement}`)
    }
  }
  if (r.notes.length) {
    lines.push('Note:')
    for (const note of r.notes) lines.push(`- ${note}`)
  }
  if (r.passages.length) {
    for (const p of r.passages) {
      lines.push(`Testo: «${[p.before, p.quote, p.after].filter(Boolean).join(' ')}» (${p.act}, ${p.article})`)
    }
  }
  lines.push('Fonti:')
  for (const s of r.sources) lines.push(`[${s.index}] ${sourceLine(s)}`)
  return lines.join('\n')
}

export function assessmentToText(a: ScopeAssessment): string {
  const header = [
    `Ambito NormaAI, regole e date verificate il ${formatDateIt(a.verifiedOn)}`,
    `Profilo: ${inputSummary(a.input)}`,
    'Primo filtro indicativo, non un parere legale.',
  ]
  return [header.join('\n'), ...a.results.map(resultToText)].join('\n\n')
}
