import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithIntl } from '@/test/i18n'

const push = vi.fn()
const loginDemo = vi.fn()

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}))

vi.mock('next/link', () => ({
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  default: ({ children, href, ...props }: any) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}))

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ login: vi.fn(), register: vi.fn(), loginDemo }),
}))

/** The page with or without a backend configured for the build. */
async function renderLogin(apiConfigured: boolean, language: 'it' | 'en' = 'it') {
  vi.resetModules()
  vi.doMock('@/lib/api', () => ({ API_CONFIGURED: apiConfigured }))
  const { default: LoginPage } = await import('../page')
  return renderWithIntl(<LoginPage />, { language })
}

describe('sign-in page', () => {
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  describe('while no backend is configured', () => {
    it('says that sign-in is suspended, since when, and promises no date', async () => {
      await renderLogin(false)
      const status = await screen.findByRole('status')
      expect(status).toHaveTextContent('Accesso agli account sospeso')
      expect(status).toHaveTextContent('Ultimo aggiornamento di questo stato: 11 novembre 2026.')
      expect(status).not.toHaveTextContent(/qualche giorno|tra pochi|a breve|domani/i)
      expect(screen.getByRole('link', { name: 'info@normaai.org' })).toHaveAttribute('href', 'mailto:info@normaai.org')
    })

    it('shows no field and no submit button: there is nothing a visitor could send', async () => {
      await renderLogin(false)
      await screen.findByRole('status')
      expect(screen.queryByLabelText(/Email/)).not.toBeInTheDocument()
      expect(screen.queryByLabelText(/Password/)).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Accedi' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /Crea l.account/ })).not.toBeInTheDocument()
    })

    it('offers the demo as the one action, and it works', async () => {
      const user = userEvent.setup()
      await renderLogin(false)
      const demo = await screen.findByRole('button', { name: 'Apri la demo con dati di esempio' })
      expect(screen.getAllByRole('button')).toHaveLength(1)
      await user.click(demo)
      expect(loginDemo).toHaveBeenCalledTimes(1)
      expect(push).toHaveBeenCalledWith('/app')
    })

    it('says the same in English', async () => {
      await renderLogin(false, 'en')
      const status = await screen.findByRole('status')
      expect(status).toHaveTextContent('Account sign-in is suspended')
      expect(status).toHaveTextContent('This status was last updated on 11 November 2026.')
    })
  })

  describe('with a backend configured', () => {
    it('shows the form with fields and an enabled submit button, and no suspension notice', async () => {
      await renderLogin(true)
      expect(await screen.findByLabelText(/Email/)).toBeEnabled()
      expect(screen.getByLabelText(/Password/)).toBeEnabled()
      expect(screen.getByRole('button', { name: 'Accedi' })).toBeEnabled()
      expect(screen.queryByRole('status')).not.toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Apri la demo con dati di esempio' })).toBeInTheDocument()
    })
  })
})
