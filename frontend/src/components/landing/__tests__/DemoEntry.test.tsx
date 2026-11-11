import { describe, it, expect, vi, beforeEach } from 'vitest'
import { existsSync } from 'node:fs'
import path from 'node:path'
import { screen, waitFor } from '@testing-library/react'
import { renderWithIntl } from '@/test/i18n'

const mocks = vi.hoisted(() => ({
  replace: vi.fn(),
  get: vi.fn(),
}))

vi.mock('next/navigation', () => ({
  // A new router object on every render, as the worst case for the effect.
  useRouter: () => ({ replace: mocks.replace, push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => '/demo',
}))

vi.mock('next/link', () => ({
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  default: ({ children, href, ...props }: any) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}))

vi.mock('@/lib/api', () => ({
  api: { get: (...args: unknown[]) => mocks.get(...args) },
}))

// happy-dom does not expose the storages as globals: the page and the test
// share these in-memory ones.
function memoryStorage(): Storage {
  const store: Record<string, string> = {}
  return {
    getItem: (key: string) => (key in store ? store[key] : null),
    setItem: (key: string, value: string) => {
      store[key] = String(value)
    },
    removeItem: (key: string) => {
      delete store[key]
    },
    clear: () => {
      for (const k of Object.keys(store)) delete store[k]
    },
    key: (i: number) => Object.keys(store)[i] ?? null,
    get length() {
      return Object.keys(store).length
    },
  }
}
vi.stubGlobal('localStorage', memoryStorage())
vi.stubGlobal('sessionStorage', memoryStorage())

import { AuthProvider, useAuth } from '@/hooks/useAuth'
import { APP_NAV } from '@/components/app/AppShell'
import { getAccessToken, isDemoMode, setDemoMode, setTokens } from '@/lib/auth'
import { DEMO_TOKENS, DEMO_USER } from '@/lib/mock-data'
import type { User } from '@/lib/types'
import { DemoEntry } from '../DemoEntry'
import { DEMO_DOCUMENT_CHECK, DEMO_HOME, demoDestination } from '../demo-entry'

/** Who the application would greet after /demo has done its work. */
function Session() {
  const { user, demoMode } = useAuth()
  return <p data-testid="session">{user ? `${demoMode ? 'demo' : 'account'}:${user.email}` : 'nobody'}</p>
}

function renderRoute(language: 'it' | 'en' = 'it') {
  return renderWithIntl(
    <AuthProvider>
      <DemoEntry />
      <Session />
    </AuthProvider>,
    { language },
  )
}

const CONTROLLA_PAGE = path.resolve(__dirname, '../../../app/app/controlla/page.tsx')

describe('demoDestination', () => {
  it('is the home of the application while the document check has no screen', () => {
    expect(demoDestination([{ href: '/app/chiedi' }, { href: '/app/clienti' }])).toBe(DEMO_HOME)
    expect(demoDestination([])).toBe('/app')
  })

  it('is the document check as soon as the navigation lists it', () => {
    expect(demoDestination([{ href: '/app/chiedi' }, { href: '/app/controlla' }])).toBe(DEMO_DOCUMENT_CHECK)
    expect(DEMO_DOCUMENT_CHECK).toBe('/app/controlla')
  })

  it('reads the navigation of this build, and that navigation matches the routes on disk', () => {
    const listed = APP_NAV.some((item) => item.href === DEMO_DOCUMENT_CHECK)
    // If this fails, /app/controlla exists without its navigation entry (or the
    // other way round) and /demo would send visitors to the wrong page.
    expect(listed).toBe(existsSync(CONTROLLA_PAGE))
    expect(demoDestination()).toBe(listed ? DEMO_DOCUMENT_CHECK : DEMO_HOME)
  })
})

describe('/demo', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('turns demo mode on like the button of the sign-in page and opens the demo', async () => {
    renderRoute()
    expect(screen.getByRole('status')).toHaveTextContent('Sto aprendo la demo con dati di esempio.')

    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith(demoDestination()))
    expect(mocks.replace).toHaveBeenCalledTimes(1)
    expect(isDemoMode()).toBe(true)
    expect(getAccessToken()).toBe(DEMO_TOKENS.access_token)
    expect(await screen.findByTestId('session')).toHaveTextContent(`demo:${DEMO_USER.email}`)
    // Demo mode never asks the backend who the visitor is.
    expect(mocks.get).not.toHaveBeenCalled()
  })

  it('offers a link to the same page in case the redirect does not happen', () => {
    renderRoute()
    expect(screen.getByRole('link', { name: 'apri la demo da qui' })).toHaveAttribute('href', demoDestination())
  })

  it('keeps an open demo open', async () => {
    setDemoMode(true)
    setTokens(DEMO_TOKENS.access_token, DEMO_TOKENS.refresh_token)
    renderRoute()

    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith(demoDestination()))
    expect(isDemoMode()).toBe(true)
    expect(getAccessToken()).toBe(DEMO_TOKENS.access_token)
  })

  it('leaves a signed-in session as it is', async () => {
    const account: User = {
      id: 'u-1',
      email: 'anna@studio.example',
      name: 'Anna Bianchi',
      role: 'member',
      organization_name: 'Studio Bianchi',
    }
    setTokens('account.access.token', 'account.refresh.token')
    mocks.get.mockResolvedValue(account)
    renderRoute()

    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith(demoDestination()))
    expect(mocks.replace).toHaveBeenCalledTimes(1)
    expect(isDemoMode()).toBe(false)
    expect(getAccessToken()).toBe('account.access.token')
    await waitFor(() => expect(screen.getByTestId('session')).toHaveTextContent('account:anna@studio.example'))
  })

  it('says what it is doing in English too', () => {
    renderRoute('en')
    expect(screen.getByRole('status')).toHaveTextContent('Opening the demo with sample data.')
    expect(screen.getByRole('link', { name: 'open the demo from here' })).toBeInTheDocument()
  })
})
