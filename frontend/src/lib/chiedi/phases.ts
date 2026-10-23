import type { Translate } from '@/i18n/types'

/**
 * The phases the stream announces (src/api/streaming/generators.py and the
 * CoVe orchestrator): draft, planning, verification, revision, validation.
 * The words of the status line live in the `chiedi.phases` messages.
 */
export const KNOWN_PHASES = ['draft', 'planning', 'verification', 'revision', 'validation'] as const

/** Before the first event (or while the demo waits for its mock) the page says it is searching. */
export function phaseLabel(phase: string | undefined, t: Translate): string {
  if (!phase) return t('chiedi.phases.searching')
  const known = (KNOWN_PHASES as readonly string[]).includes(phase)
  return known ? t(`chiedi.phases.${phase}`) : t('chiedi.phases.processing')
}
