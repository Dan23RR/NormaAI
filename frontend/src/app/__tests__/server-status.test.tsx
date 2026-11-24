import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { IntlWrapper } from '@/test/i18n'
import { renderServerPage, setServerLanguage } from '@/test/server-page'

/**
 * What the public pages say about the application server must follow the
 * build: while no backend is configured (NEXT_PUBLIC_API_BASE_URL empty) they
 * say, with a date, that accounts are suspended and no backup runs; once one
 * is configured those lines go away by themselves, and nothing is left that
 * says the server is off. The home page, the privacy, security and method
 * pages are rendered with the flag both ways.
 */

vi.mock('next-intl/server', () => import('@/test/server-page').then((m) => m.nextIntlServerMock))

vi.mock('next/link', () => ({
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  default: ({ children, href, ...props }: any) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}))

// The header only asks whether a session exists.
vi.mock('@/lib/auth', () => ({ getAccessToken: () => null }))

const PAGES = {
  home: () => import('../page'),
  privacy: () => import('../privacy/page'),
  security: () => import('../security/page'),
  metodo: () => import('../metodo/page'),
} as const

/** The text of a page built with or without a backend. */
async function pageText(name: keyof typeof PAGES, backendConfigured: boolean): Promise<string> {
  vi.resetModules()
  vi.doMock('@/lib/service-status', () => ({
    BACKEND_CONFIGURED: backendConfigured,
    SERVICE_STATUS_ON: new Date(Date.UTC(2026, 10, 11)),
  }))
  const { default: Page } = (await PAGES[name]()) as { default: () => ReactElement | Promise<ReactElement> }
  setServerLanguage('it')
  const tree = await renderServerPage(<Page />)
  const { container } = render(<IntlWrapper language="it">{tree}</IntlWrapper>)
  return container.textContent ?? ''
}

const SUSPENDED = 'Gli account sono sospesi mentre il server dell’applicazione viene spostato.'
const BACKUP_OFF = 'Finché il server di produzione è spento nessun backup è in corso'
// Words that are true only while the server is off ("spento per impostazione
// predefinita" describes settings, not the server, and stays).
const SERVER_OFF = /server di produzione (oggi )?è spento|sono sospesi|sospeso|Stato all'11 novembre 2026/

afterEach(() => {
  cleanup()
  vi.doUnmock('@/lib/service-status')
})

describe('without a backend', () => {
  it('the home page carries its dated status line', async () => {
    const text = await pageText('home', false)
    expect(text).toContain("Stato all'11 novembre 2026.")
    expect(text).toContain('gli account, e con loro le risposte sul corpus reale, sono sospesi')
  })

  it.each(['privacy', 'security'] as const)('%s says that accounts are suspended and no backup runs', async (name) => {
    const text = await pageText(name, false)
    expect(text).toContain(SUSPENDED)
    expect(text).toContain('Ultimo aggiornamento di questo stato: 11 novembre 2026.')
    expect(text).toContain(BACKUP_OFF)
  })

  it('the method page says that accounts are suspended', async () => {
    expect(await pageText('metodo', false)).toContain(SUSPENDED)
  })
})

describe('with a backend', () => {
  it.each(Object.keys(PAGES) as Array<keyof typeof PAGES>)('%s says nothing about a server that is off', async (name) => {
    const text = await pageText(name, true)
    expect(text).not.toContain(SUSPENDED)
    expect(text).not.toContain(BACKUP_OFF)
    expect(text).not.toMatch(SERVER_OFF)
  })
})

describe('in either state', () => {
  it.each(Object.keys(PAGES) as Array<keyof typeof PAGES>)('%s claims no server running today', async (name) => {
    for (const configured of [false, true]) {
      const text = await pageText(name, configured)
      expect(text).not.toMatch(/girano su un server Hetzner|Oggi questi eventi|È lì che l’applicazione conserva i dati/)
      cleanup()
    }
  })
})
