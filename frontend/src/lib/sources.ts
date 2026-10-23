/**
 * A source as the interface shows it: the act, the article, the exact
 * passage and whether that passage was found in the official text.
 */
export type SourceStatus = 'verified' | 'unverified' | 'pending'

export interface Source {
  id: string
  /** 1-based number used as the in-text marker, e.g. [1]. */
  index: number
  /** Act title as cited: "Regolamento (UE) 2024/1689". */
  act: string
  /** "art. 50, par. 1" */
  article?: string
  celex?: string
  /** Link to EUR-Lex or Normattiva. */
  url?: string
  /** The exact passage, as it appears in the official text. */
  quote?: string
  status: SourceStatus
  /** ISO date of the verification against the official text. */
  verifiedAt?: string
  /** Where the text comes from, e.g. "EUR-Lex" or "Normattiva". */
  origin?: string
}

export const SOURCE_STATUS_LABEL: Record<SourceStatus, string> = {
  verified: 'Verificata nel testo ufficiale',
  unverified: 'Non trovata nel testo ufficiale',
  pending: 'Verifica in corso',
}

/** EUR-Lex URL for a CELEX number, in the given language. */
export function eurlexUrl(celex: string, lang: 'IT' | 'EN' = 'IT'): string {
  return `https://eur-lex.europa.eu/legal-content/${lang}/TXT/?uri=CELEX:${encodeURIComponent(celex)}`
}
