import type { ReactElement, ReactNode } from 'react'
import { render, type RenderOptions, type RenderResult } from '@testing-library/react'
import { NextIntlClientProvider, createTranslator, type AbstractIntlMessages } from 'next-intl'
import it from '../../messages/it.json'
import en from '../../messages/en.json'
import { LOCALES, type Language } from '@/i18n/config'
import type { TextContext, Translate } from '@/i18n/types'

/** The real messages, so tests see the words people see. */
export const MESSAGES: Record<Language, AbstractIntlMessages> = {
  it: it as AbstractIntlMessages,
  en: en as AbstractIntlMessages,
}

export const TIME_ZONE = 'Europe/Rome'

export function IntlWrapper({ children, language = 'it' }: { children: ReactNode; language?: Language }) {
  return (
    <NextIntlClientProvider locale={LOCALES[language]} messages={MESSAGES[language]} timeZone={TIME_ZONE}>
      {children}
    </NextIntlClientProvider>
  )
}

/** `render` with the messages of a language around the component (Italian by default). */
export function renderWithIntl(
  ui: ReactElement,
  { language = 'it', ...options }: Omit<RenderOptions, 'wrapper'> & { language?: Language } = {},
): RenderResult {
  return render(ui, {
    ...options,
    wrapper: ({ children }) => <IntlWrapper language={language}>{children}</IntlWrapper>,
  })
}

/** The root translator of a language, for library code (scope rules, calendar, clipboard). */
export function translatorFor(language: Language = 'it'): Translate {
  return createTranslator({
    locale: LOCALES[language],
    messages: MESSAGES[language] as Record<string, unknown>,
    timeZone: TIME_ZONE,
  }) as unknown as Translate
}

export function textContextFor(language: Language = 'it'): TextContext {
  return { locale: LOCALES[language], t: translatorFor(language) }
}
