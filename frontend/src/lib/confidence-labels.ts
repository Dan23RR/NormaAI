/**
 * Qualitative labels for the model's confidence.
 *
 * RULE: the numeric confidence score is never shown to the person. It is
 * mapped to a label, and the label uses the design tokens (DESIGN.md):
 * `union` for an answer that rests on the sources, `warn` when a check is
 * advised. Never `ok` (reads as a certification) and never `bad` (reads as
 * a legal failure).
 */

export type ConfidenceLevel = 'high' | 'medium' | 'low'

export interface ConfidenceLabelConfig {
  level: ConfidenceLevel
  label: string
  sublabel: string
  /** Text colour class. */
  color: string
  /** Background class (tinted). */
  bg: string
  /** Border class (tinted). */
  border: string
}

const THRESHOLDS = {
  high: 0.85,
  medium: 0.65,
} as const

const TONE = {
  union: { color: 'text-union', bg: 'bg-union/10', border: 'border-union/20' },
  warn: { color: 'text-warn', bg: 'bg-warn/10', border: 'border-warn/20' },
  neutral: { color: 'text-ink-2', bg: 'bg-surface-3', border: 'border-rule' },
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
      sublabel: 'La risposta poggia su passaggi normativi diretti',
      ...TONE.union,
    }
  }
  if (score >= THRESHOLDS.medium) {
    return {
      level: 'medium',
      label: 'Affidabilità media',
      sublabel: 'Fonti parziali: verifica consigliata',
      ...TONE.warn,
    }
  }
  return {
    level: 'low',
    label: 'Richiede verifica',
    sublabel: 'Analisi preliminare: serve la revisione di un esperto',
    ...TONE.warn,
  }
}

/**
 * Map an overall compliance score (0-100) to a qualitative assessment.
 * Same logic as the confidence label, for gap analysis results.
 * The numeric score is NEVER shown to the user.
 */
export function getComplianceLabel(score: number): ConfidenceLabelConfig {
  if (score >= 70) {
    return {
      level: 'high',
      label: 'Buon livello di conformità',
      sublabel: "L'organizzazione presenta un solido grado di adempimento",
      ...TONE.union,
    }
  }
  if (score >= 40) {
    return {
      level: 'medium',
      label: 'Conformità parziale',
      sublabel: 'Aree significative richiedono intervento',
      ...TONE.warn,
    }
  }
  return {
    level: 'low',
    label: 'Gap significativi rilevati',
    sublabel: 'Azione prioritaria necessaria su più requisiti',
    ...TONE.warn,
  }
}

/**
 * Compliance status colours on the design tokens.
 *
 * COMPLIANT = union (informative, not "approved")
 * PARTIALLY_COMPLIANT = warn (caution)
 * NON_COMPLIANT = warn (action needed, not "failed")
 * IN_EVOLUTION = union (in progress)
 * NOT_APPLICABLE = neutral
 */
export const COMPLIANCE_STATUS_COLORS = {
  COMPLIANT: { color: TONE.union.color, bg: TONE.union.bg, label: 'Conforme' },
  PARTIALLY_COMPLIANT: { color: TONE.warn.color, bg: TONE.warn.bg, label: 'Parziale' },
  NON_COMPLIANT: { color: TONE.warn.color, bg: TONE.warn.bg, label: 'Non conforme' },
  NOT_APPLICABLE: { color: TONE.neutral.color, bg: TONE.neutral.bg, label: 'Non applicabile' },
  IN_EVOLUTION: { color: TONE.union.color, bg: TONE.union.bg, label: 'In evoluzione' },
} as const
