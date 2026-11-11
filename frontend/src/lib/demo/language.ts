import { DEFAULT_LANGUAGE, LOCALE_COOKIE, isLanguage, languageOf, type Language } from '@/i18n/config'

/**
 * The language the demo data is written in: the language of the interface.
 * The cookie the server renders from comes first, then the `lang` of the
 * document; outside a browser (tests, server) it is Italian.
 */
export function demoLanguage(): Language {
  if (typeof document === 'undefined') return DEFAULT_LANGUAGE
  const cookie = document.cookie.match(new RegExp(`(?:^|;\\s*)${LOCALE_COOKIE.replace('.', '\\.')}=([^;]*)`))
  if (cookie) {
    const value = decodeURIComponent(cookie[1])
    if (isLanguage(value)) return value
  }
  const lang = document.documentElement.lang
  return lang ? languageOf(lang) : DEFAULT_LANGUAGE
}

/**
 * One record whose fields follow the interface language at the moment they
 * are read. The demo constants (`DEMO_ALERTS`, ...) are plain exports that the
 * API client hands to the pages as they are: this keeps them in the language
 * of the reader without the client having to know about languages.
 */
export function localized<T extends object>(variants: Record<Language, T>): T {
  return new Proxy(variants[DEFAULT_LANGUAGE], {
    get: (_target, key) => Reflect.get(variants[demoLanguage()], key),
  })
}
