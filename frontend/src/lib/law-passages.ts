/**
 * Passages of law quoted verbatim by the interface. A quote keeps the
 * language of the official text it was taken from, whatever the language
 * of the interface: these are not translated.
 */
export interface QuotedPassage {
  quote: string
  before?: string
  after?: string
  /** Language of the quoted text (BCP 47). */
  lang: string
  celex: string
}

/** Regolamento (UE) 2024/1689, art. 50, par. 1, Italian official text. */
export const AI_ACT_ART_50_1_IT: QuotedPassage = {
  before:
    'I fornitori garantiscono che i sistemi di IA destinati a interagire direttamente con le persone fisiche sono progettati e sviluppati in modo tale che le persone fisiche interessate',
  quote: 'siano informate del fatto di stare interagendo con un sistema di IA',
  after:
    'a meno che ciò non risulti evidente dal punto di vista di una persona fisica ragionevolmente informata, attenta e avveduta',
  lang: 'it',
  celex: '32024R1689',
}
