/**
 * Enterprise confidence label mapping.
 *
 * RULE: Never expose numerical AI confidence scores to end users.
 * Map to qualitative labels with blue/neutral palette (not traffic lights).
 *
 * Palette rationale:
 * - Blue = informative (not "approved" like green would imply)
 * - Amber = caution / needs attention
 * - Orange = action required
 * - Never green (implies certification) or red (implies legal failure)
 */

export type ConfidenceLevel = 'high' | 'medium' | 'low'

export interface ConfidenceLabelConfig {
  level: ConfidenceLevel
  label: string
  sublabel: string
  color: string
  bg: string
  border: string
}

const THRESHOLDS = {
  high: 0.85,
  medium: 0.65,
} as const

/**
 * Map a numeric confidence score (0-1) to a qualitative label.
 * The numeric score is NEVER shown to the user.
 */
export function getConfidenceLabel(score: number): ConfidenceLabelConfig {
  if (score >= THRESHOLDS.high) {
    return {
      level: 'high',
      label: 'Alta affidabilità',
      sublabel: 'Basata su fonti normative dirette',
      color: 'text-blue-400',
      bg: 'bg-blue-400/10',
      border: 'border-blue-400/20',
    }
  }
  if (score >= THRESHOLDS.medium) {
    return {
      level: 'medium',
      label: 'Affidabilità media',
      sublabel: 'Fonti parziali — verifica raccomandata',
      color: 'text-amber-400',
      bg: 'bg-amber-400/10',
      border: 'border-amber-400/20',
    }
  }
  return {
    level: 'low',
    label: 'Richiede verifica',
    sublabel: 'Analisi preliminare — revisione esperto necessaria',
    color: 'text-orange-400',
    bg: 'bg-orange-400/10',
    border: 'border-orange-400/20',
  }
}

/**
 * Map an overall compliance score to a qualitative assessment.
 * Same logic as confidence but for gap analysis overall scores (0-100).
 *
 * NEVER show the numeric score to the user.
 */
export function getComplianceLabel(score: number): ConfidenceLabelConfig {
  if (score >= 70) {
    return {
      level: 'high',
      label: 'Buon livello di conformità',
      sublabel: 'L\'organizzazione presenta un solido grado di adempimento',
      color: 'text-blue-400',
      bg: 'bg-blue-400/10',
      border: 'border-blue-400/20',
    }
  }
  if (score >= 40) {
    return {
      level: 'medium',
      label: 'Conformità parziale',
      sublabel: 'Aree significative richiedono intervento',
      color: 'text-amber-400',
      bg: 'bg-amber-400/10',
      border: 'border-amber-400/20',
    }
  }
  return {
    level: 'low',
    label: 'Gap significativi rilevati',
    sublabel: 'Azione prioritaria necessaria su più requisiti',
    color: 'text-orange-400',
    bg: 'bg-orange-400/10',
    border: 'border-orange-400/20',
  }
}

/**
 * Compliance status colors — blue/neutral palette (no traffic lights).
 *
 * COMPLIANT = blue (informative, not "approved")
 * PARTIALLY_COMPLIANT = amber (caution)
 * NON_COMPLIANT = orange (action needed, not "failed")
 * IN_EVOLUTION = sky (in progress)
 * NOT_APPLICABLE = slate (neutral)
 */
export const COMPLIANCE_STATUS_COLORS = {
  COMPLIANT: { color: 'text-blue-400', bg: 'bg-blue-400/10', label: 'Conforme' },
  PARTIALLY_COMPLIANT: { color: 'text-amber-400', bg: 'bg-amber-400/10', label: 'Parziale' },
  NON_COMPLIANT: { color: 'text-orange-400', bg: 'bg-orange-400/10', label: 'Non conforme' },
  NOT_APPLICABLE: { color: 'text-slate-500', bg: 'bg-slate-500/10', label: 'N/A' },
  IN_EVOLUTION: { color: 'text-sky-400', bg: 'bg-sky-400/10', label: 'In evoluzione' },
} as const
