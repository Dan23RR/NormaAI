import type { BadgeTone } from '@/components/ui'
import type { Translate } from '@/i18n/types'
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

export function complianceAssessment(overallScore: number, t: Translate): Assessment {
  const cfg = getComplianceLabel(overallScore, t)
  return { label: cfg.label, sublabel: cfg.sublabel, tone: cfg.level === 'high' ? 'union' : 'warn' }
}

export function confidenceAssessment(confidenceScore: number, t: Translate): Assessment {
  const cfg = getConfidenceLabel(confidenceScore, t)
  return { label: cfg.label, sublabel: cfg.sublabel, tone: cfg.level === 'high' ? 'union' : 'warn' }
}

export const STATUS_TONE: Record<ComplianceStatus, BadgeTone> = {
  COMPLIANT: 'union',
  PARTIALLY_COMPLIANT: 'warn',
  NON_COMPLIANT: 'bad',
  NOT_APPLICABLE: 'neutral',
  IN_EVOLUTION: 'neutral',
}

export function statusMeta(status: string | undefined, t: Translate): { label: string; tone: BadgeTone } {
  if (status && status in STATUS_TONE) {
    return { label: t(`ui.compliance.status.${status}`), tone: STATUS_TONE[status as ComplianceStatus] }
  }
  return { label: status ? status.replace(/_/g, ' ').toLowerCase() : t('ui.notAvailable'), tone: 'neutral' }
}

export const PRIORITY_TONE: Record<string, BadgeTone> = {
  P1: 'bad',
  P2: 'warn',
  P3: 'union',
  P4: 'neutral',
}

const EFFORTS = ['LOW', 'MEDIUM', 'HIGH']

export function effortLabel(effort: string | undefined, t: Translate): string {
  if (!effort) return ''
  const key = effort.trim().toUpperCase()
  return EFFORTS.includes(key) ? t(`ui.compliance.effort.${key}`) : effort
}

/** Order and labels of the status counters under the assessment. */
export const STATUS_SUMMARY_KEYS: Array<{ key: string; status: ComplianceStatus }> = [
  { key: 'compliant', status: 'COMPLIANT' },
  { key: 'partially_compliant', status: 'PARTIALLY_COMPLIANT' },
  { key: 'non_compliant', status: 'NON_COMPLIANT' },
  { key: 'in_evolution', status: 'IN_EVOLUTION' },
  { key: 'not_applicable', status: 'NOT_APPLICABLE' },
]
