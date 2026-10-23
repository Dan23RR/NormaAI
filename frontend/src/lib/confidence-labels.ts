/**
 * Qualitative labels for the model's confidence.
 *
 * RULE: the numeric confidence score is never shown to the person. It is
 * mapped to a label, and the label uses the design tokens (DESIGN.md):
 * `union` for an answer that rests on the sources, `warn` when a check is
 * advised. Never `ok` (reads as a certification) and never `bad` (reads as
 * a legal failure). The words live in the `ui.confidence` and
 * `ui.compliance` messages.
 */
import type { Translate } from '@/i18n/types'

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
} as const

export function confidenceLevel(score: number): ConfidenceLevel {
  if (score >= THRESHOLDS.high) return 'high'
  if (score >= THRESHOLDS.medium) return 'medium'
  return 'low'
}

/**
 * Map a numeric confidence score (0-1) to a qualitative label.
 * The numeric score is NEVER shown to the user.
 */
export function getConfidenceLabel(score: number, t: Translate): ConfidenceLabelConfig {
  const level = confidenceLevel(score)
  return {
    level,
    label: t(`ui.confidence.${level}.label`),
    sublabel: t(`ui.confidence.${level}.sublabel`),
    ...(level === 'high' ? TONE.union : TONE.warn),
  }
}

export function complianceLevel(score: number): ConfidenceLevel {
  if (score >= 70) return 'high'
  if (score >= 40) return 'medium'
  return 'low'
}

/**
 * Map an overall compliance score (0-100) to a qualitative assessment.
 * Same logic as the confidence label, for gap analysis results.
 * The numeric score is NEVER shown to the user.
 */
export function getComplianceLabel(score: number, t: Translate): ConfidenceLabelConfig {
  const level = complianceLevel(score)
  return {
    level,
    label: t(`ui.compliance.${level}.label`),
    sublabel: t(`ui.compliance.${level}.sublabel`),
    ...(level === 'high' ? TONE.union : TONE.warn),
  }
}
