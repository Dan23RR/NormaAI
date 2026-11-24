import { cloneElement, isValidElement, type ReactElement, type ReactNode } from 'react'
import { createFormatter, createTranslator } from 'next-intl'
import { LOCALES, type Language } from '@/i18n/config'
import { MESSAGES, TIME_ZONE } from './i18n'

/**
 * Test doubles for the pages that are async Server Components (privacy,
 * terms, cookie, security, method): `next-intl/server` answered from the real
 * message files, and a walker that awaits the async components of a tree so
 * that the result can be rendered like any other element.
 *
 * In a test file:
 *
 *   vi.mock('next-intl/server', () => import('@/test/server-page').then((m) => m.nextIntlServerMock))
 *   setServerLanguage('en')
 *   render(<IntlWrapper language="en">{await renderServerPage(<PrivacyPage />)}</IntlWrapper>)
 *
 * A missing message or a missing argument THROWS here (the runtime would only
 * log it and print the key), so a page that asks for a key the message files
 * do not have fails its test.
 */

let language: Language = 'it'

export function setServerLanguage(next: Language): void {
  language = next
}

function fail(error: unknown): never {
  throw error instanceof Error ? error : new Error(String(error))
}

export const nextIntlServerMock = {
  getTranslations: async (namespace?: string) =>
    createTranslator({
      locale: LOCALES[language],
      messages: MESSAGES[language] as Record<string, unknown>,
      namespace: namespace as never,
      timeZone: TIME_ZONE,
      onError: fail,
    }),
  getFormatter: async () => createFormatter({ locale: LOCALES[language], timeZone: TIME_ZONE, onError: fail }),
  getLocale: async () => LOCALES[language],
  getMessages: async () => MESSAGES[language],
}

type AnyProps = { children?: ReactNode }

function isAsyncComponent(type: unknown): type is (props: unknown) => Promise<ReactNode> {
  return typeof type === 'function' && type.constructor.name === 'AsyncFunction'
}

/** The same tree with every async component awaited and replaced by what it returned. */
export async function renderServerPage(node: ReactNode): Promise<ReactNode> {
  if (Array.isArray(node)) return Promise.all(node.map(renderServerPage))
  if (!isValidElement(node)) return node
  const element = node as ReactElement<AnyProps>
  if (isAsyncComponent(element.type)) return renderServerPage(await element.type(element.props))
  if (element.props.children === undefined) return element
  return cloneElement(element, { children: await renderServerPage(element.props.children) })
}
