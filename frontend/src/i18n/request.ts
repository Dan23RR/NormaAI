import { cookies } from 'next/headers'
import { getRequestConfig } from 'next-intl/server'
import { LOCALE_COOKIE, localeOf, toLanguage } from './config'

/**
 * No locale in the URL: the language comes from the `normaai.locale` cookie
 * ("it" | "en", Italian by default) and the messages from messages/<lang>.json.
 * Every page is rendered per request, which is what reading a cookie implies.
 */
export default getRequestConfig(async () => {
  const store = await cookies()
  const language = toLanguage(store.get(LOCALE_COOKIE)?.value)
  return {
    locale: localeOf(language),
    messages: (await import(`../../messages/${language}.json`)).default,
    timeZone: 'Europe/Rome',
  }
})
