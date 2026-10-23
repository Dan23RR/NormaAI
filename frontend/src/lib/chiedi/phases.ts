/**
 * The phases the stream announces (src/api/streaming/generators.py and the
 * CoVe orchestrator), in the words the page uses for its status line.
 */
export const PHASE_LABELS: Record<string, string> = {
  draft: 'Scrittura della risposta',
  planning: 'Pianificazione delle verifiche',
  verification: 'Verifica delle affermazioni',
  revision: 'Revisione della risposta',
  validation: 'Verifica delle citazioni',
}

/** Before the first event, or while the demo waits for its mock. */
export const SEARCHING_LABEL = 'Cerco nei testi'

export function phaseLabel(phase: string | undefined): string {
  if (!phase) return SEARCHING_LABEL
  return PHASE_LABELS[phase] ?? 'Elaborazione in corso'
}
