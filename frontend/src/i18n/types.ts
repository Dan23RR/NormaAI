import type { TranslationValues } from 'next-intl'
import type { Locale } from './config'

/**
 * The translator a library function receives: the root `t` of next-intl
 * (no namespace), so every key is reachable with its full path.
 */
export interface Translate {
  (key: string, values?: TranslationValues): string
  has(key: string): boolean
  raw(key: string): unknown
}

/** What a library needs to write text for the person: the locale for dates and numbers, the translator for the words. */
export interface TextContext {
  locale: Locale
  t: Translate
}
