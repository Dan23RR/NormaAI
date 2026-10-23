/**
 * The two languages of the interface.
 *
 * The language code ("it" | "en") is what the cookie, the localStorage key
 * and the selectors use, and the name of the messages file. The locale is
 * the BCP 47 tag next-intl formats with: Italian conventions for Italian,
 * British English for English ("2 August 2026", "1,200", "€450,000,000").
 */
export const LANGUAGES = ['it', 'en'] as const
export type Language = (typeof LANGUAGES)[number]

export const LOCALES = { it: 'it-IT', en: 'en-GB' } as const
export type Locale = (typeof LOCALES)[Language]

export const DEFAULT_LANGUAGE: Language = 'it'

/** Cookie read by the server on every request (src/i18n/request.ts): one year, SameSite=Lax. */
export const LOCALE_COOKIE = 'normaai.locale'
export const LOCALE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365
/** Key the previous interface used in localStorage; still written for compatibility. */
export const LOCALE_STORAGE_KEY = 'normaai_locale'

export function isLanguage(value: unknown): value is Language {
  return typeof value === 'string' && (LANGUAGES as readonly string[]).includes(value)
}

/** Any value (cookie, storage, query) as a language; anything unknown is Italian. */
export function toLanguage(value: unknown): Language {
  return isLanguage(value) ? value : DEFAULT_LANGUAGE
}

export function localeOf(language: Language): Locale {
  return LOCALES[language]
}

/** "en-GB" -> "en"; anything else -> "it". */
export function languageOf(locale: string): Language {
  return locale.toLowerCase().startsWith('en') ? 'en' : 'it'
}

/** The language of the EUR-Lex text to link to. */
export function eurlexLang(locale: string): 'IT' | 'EN' {
  return languageOf(locale) === 'en' ? 'EN' : 'IT'
}
