import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithIntl } from '@/test/i18n'
import { CookieBanner } from '../CookieBanner'

vi.mock('next/link', () => ({
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  default: ({ children, href, ...props }: any) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}))

// Same in-memory stand-in the other suites use: the runtime under test has no
// browser storage of its own.
function memoryStorage(): Storage {
  let store: Record<string, string> = {}
  return {
    getItem: (key: string) => (key in store ? store[key] : null),
    setItem: (key: string, value: string) => {
      store[key] = String(value)
    },
    removeItem: (key: string) => {
      delete store[key]
    },
    clear: () => {
      store = {}
    },
    key: (i: number) => Object.keys(store)[i] ?? null,
    get length() {
      return Object.keys(store).length
    },
  }
}
vi.stubGlobal('localStorage', memoryStorage())

const DISMISS_KEY = 'normaai.cookie-banner.dismissed'

describe('CookieBanner', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('shows the notice with the link to the cookie policy on a first visit', async () => {
    renderWithIntl(<CookieBanner />)
    const notice = await screen.findByRole('region', { name: 'Informativa cookie' })
    expect(notice).toHaveTextContent('un solo cookie tecnico')
    expect(screen.getByRole('link', { name: 'cookie policy' })).toHaveAttribute('href', '/cookie')
  })

  it('is part of the page flow on small screens, never a fixed overlay', async () => {
    // On a 390 x 844 phone a fixed bar covered the last controls of the page
    // (the demo button of the sign-in page). In the flow it cannot cover
    // anything; from `sm` up it is sticky, which still takes its own space.
    renderWithIntl(<CookieBanner />)
    const notice = await screen.findByRole('region', { name: 'Informativa cookie' })
    const classes = notice.className.split(/\s+/)
    expect(classes).not.toContain('fixed')
    expect(classes).not.toContain('absolute')
    expect(classes.filter((c) => /(^|:)(fixed|absolute)$/.test(c))).toEqual([])
    expect(classes).toContain('sm:sticky')
  })

  it('goes away, and stays away, after "Ho capito"', async () => {
    const user = userEvent.setup()
    const { unmount } = renderWithIntl(<CookieBanner />)
    await user.click(await screen.findByRole('button', { name: 'Ho capito' }))
    expect(screen.queryByRole('region', { name: 'Informativa cookie' })).not.toBeInTheDocument()
    expect(localStorage.getItem(DISMISS_KEY)).toBe('true')

    unmount()
    renderWithIntl(<CookieBanner />)
    expect(screen.queryByRole('region', { name: 'Informativa cookie' })).not.toBeInTheDocument()
  })
})
