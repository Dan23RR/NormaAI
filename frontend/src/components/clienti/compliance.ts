import type { BadgeTone } from '@/components/ui'
import type { ComplianceStatus } from '@/lib/types'
import { getComplianceLabel, getConfidenceLabel } from '@/lib/confidence-labels'

/**
 * Qualitative reading of an analysis. The numeric scores are never shown:
 * the thresholds come from confidence-labels.ts, the colours are mapped
 * here to the design tokens (union for a good level, warn otherwise).
 */
export interface Assessment {
  label: string
  sublabel: string
  tone: 'union' | 'warn'
}

export function complianceAssessment(overallScore: number): Assessment {
  const cfg = getComplianceLabel(overallScore)
  return { label: cfg.label, sublabel: cfg.sublabel, tone: cfg.level === 'high' ? 'union' : 'warn' }
}

export function confidenceAssessment(confidenceScore: number): Assessment {
  const cfg = getConfidenceLabel(confidenceScore)
  return { label: cfg.label, sublabel: cfg.sublabel, tone: cfg.level === 'high' ? 'union' : 'warn' }
}

export const STATUS_META: Record<ComplianceStatus, { label: string; tone: BadgeTone }> = {
  COMPLIANT: { label: 'Conforme', tone: 'union' },
  PARTIALLY_COMPLIANT: { label: 'Parziale', tone: 'warn' },
  NON_COMPLIANT: { label: 'Non conforme', tone: 'bad' },
  NOT_APPLICABLE: { label: 'N/A', tone: 'neutral' },
  IN_EVOLUTION: { label: 'In evoluzione', tone: 'neutral' },
}

export function statusMeta(status: string | undefined): { label: string; tone: BadgeTone } {
  if (status && status in STATUS_META) return STATUS_META[status as ComplianceStatus]
  return { label: status ? status.replace(/_/g, ' ').toLowerCase() : 'n.d.', tone: 'neutral' }
}

export const PRIORITY_TONE: Record<string, BadgeTone> = {
  P1: 'bad',
  P2: 'warn',
  P3: 'union',
  P4: 'neutral',
}

const EFFORT_LABEL: Record<string, string> = {
  LOW: 'Basso',
  MEDIUM: 'Medio',
  HIGH: 'Alto',
}

export function effortLabel(effort: string | undefined): string {
  if (!effort) return ''
  return EFFORT_LABEL[effort.trim().toUpperCase()] ?? effort
}

/** Order and labels of the status counters under the assessment. */
export const STATUS_SUMMARY_KEYS: Array<{ key: string; status: ComplianceStatus }> = [
  { key: 'compliant', status: 'COMPLIANT' },
  { key: 'partially_compliant', status: 'PARTIALLY_COMPLIANT' },
  { key: 'non_compliant', status: 'NON_COMPLIANT' },
  { key: 'in_evolution', status: 'IN_EVOLUTION' },
  { key: 'not_applicable', status: 'NOT_APPLICABLE' },
]
