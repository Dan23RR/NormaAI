import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithIntl } from '@/test/i18n'
import { ApiError } from '@/lib/api-error'

const mocks = vi.hoisted(() => ({
  token: '',
  requestPasswordReset: vi.fn(),
  resetPassword: vi.fn(),
  clearTokens: vi.fn(),
}))

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(mocks.token ? { token: mocks.token } : {}),
}))

vi.mock('next/link', () => ({
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  default: ({ children, href, ...props }: any) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}))

vi.mock('@/lib/auth', () => ({ clearTokens: () => mocks.clearTokens() }))

/** The page with or without a backend, at /reset-password or /reset-password?token=... */
async function renderPage({ apiConfigured = true, token = '', language = 'it' as 'it' | 'en' } = {}) {
  mocks.token = token
  vi.resetModules()
  vi.doMock('@/lib/api', () => ({
    API_CONFIGURED: apiConfigured,
    api: {
      requestPasswordReset: (...args: unknown[]) => mocks.requestPasswordReset(...args),
      resetPassword: (...args: unknown[]) => mocks.resetPassword(...args),
    },
  }))
  const { default: Page } = await import('../page')
  return renderWithIntl(<Page />, { language })
}

describe('reset password page', () => {
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('without a backend says to write, and shows no form', async () => {
    await renderPage({ apiConfigured: false })
    const status = await screen.findByRole('status')
    expect(status).toHaveTextContent('per reimpostare la password scrivi a info@normaai.org')
    expect(screen.getByRole('link', { name: 'info@normaai.org' })).toHaveAttribute('href', 'mailto:info@normaai.org')
    expect(screen.queryByLabelText(/Email/)).not.toBeInTheDocument()
  })

  it('asks for a link and gives the same answer whatever the address', async () => {
    const user = userEvent.setup()
    mocks.requestPasswordReset.mockResolvedValue(undefined)
    await renderPage()
    await user.type(await screen.findByLabelText(/Email/), ' anna@studio.it ')
    await user.click(screen.getByRole('button', { name: 'Invia il link' }))
    expect(mocks.requestPasswordReset).toHaveBeenCalledWith('anna@studio.it')
    const status = await screen.findByRole('status')
    expect(status).toHaveTextContent('Controlla la posta')
    expect(status).toHaveTextContent('Se anna@studio.it corrisponde a un account attivo')
    expect(screen.getByRole('link', { name: 'Torna all’accesso' })).toHaveAttribute('href', '/login')
  })

  it('shows what the server says when the request fails', async () => {
    const user = userEvent.setup()
    mocks.requestPasswordReset.mockRejectedValue(new ApiError('requestFailed', { detail: 'Troppe richieste. Riprova tra 1 minuto.' }))
    await renderPage()
    await user.type(await screen.findByLabelText(/Email/), 'anna@studio.it')
    await user.click(screen.getByRole('button', { name: 'Invia il link' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Troppe richieste. Riprova tra 1 minuto.')
  })

  it('with the token of the link checks the two passwords before sending them', async () => {
    const user = userEvent.setup()
    await renderPage({ token: 'user.secret-of-the-link' })
    expect(await screen.findByRole('heading', { name: 'Scegli una nuova password' })).toBeInTheDocument()
    await user.type(screen.getByLabelText(/^Nuova password/), 'corta')
    await user.type(screen.getByLabelText(/Ripeti la nuova password/), 'corta')
    await user.click(screen.getByRole('button', { name: 'Salva la nuova password' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('almeno 8 caratteri')

    await user.clear(screen.getByLabelText(/^Nuova password/))
    await user.type(screen.getByLabelText(/^Nuova password/), 'lunga-abbastanza-1')
    await user.clear(screen.getByLabelText(/Ripeti la nuova password/))
    await user.type(screen.getByLabelText(/Ripeti la nuova password/), 'lunga-abbastanza-2')
    await user.click(screen.getByRole('button', { name: 'Salva la nuova password' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Le due password non coincidono.')
    expect(mocks.resetPassword).not.toHaveBeenCalled()
  })

  it('saves the new password, forgets this browser’s session and sends to sign-in', async () => {
    const user = userEvent.setup()
    mocks.resetPassword.mockResolvedValue({ status: 'password_changed', email: 'anna@studio.it' })
    await renderPage({ token: 'user.secret-of-the-link' })
    await user.type(await screen.findByLabelText(/^Nuova password/), 'lunga-abbastanza')
    await user.type(screen.getByLabelText(/Ripeti la nuova password/), 'lunga-abbastanza')
    await user.click(screen.getByRole('button', { name: 'Salva la nuova password' }))
    expect(mocks.resetPassword).toHaveBeenCalledWith('user.secret-of-the-link', 'lunga-abbastanza')
    const status = await screen.findByRole('status')
    expect(status).toHaveTextContent('Password aggiornata')
    expect(status).toHaveTextContent('La password di anna@studio.it è cambiata')
    expect(mocks.clearTokens).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('link', { name: 'Accedi' })).toHaveAttribute('href', '/login')
  })

  it('an expired link says so and offers a new one', async () => {
    const user = userEvent.setup()
    mocks.resetPassword.mockRejectedValue(
      new ApiError('requestFailed', { detail: 'Il link per reimpostare la password non è valido o è scaduto.' }),
    )
    await renderPage({ token: 'user.old-secret' })
    await user.type(await screen.findByLabelText(/^Nuova password/), 'lunga-abbastanza')
    await user.type(screen.getByLabelText(/Ripeti la nuova password/), 'lunga-abbastanza')
    await user.click(screen.getByRole('button', { name: 'Salva la nuova password' }))
    const status = await screen.findByRole('status')
    expect(status).toHaveTextContent('Link non valido')
    expect(status).toHaveTextContent('non è valido o è scaduto')
    expect(screen.getByRole('link', { name: 'Chiedi un nuovo link' })).toHaveAttribute('href', '/reset-password')
    expect(mocks.clearTokens).not.toHaveBeenCalled()
  })

  it('speaks English too', async () => {
    const user = userEvent.setup()
    mocks.requestPasswordReset.mockResolvedValue(undefined)
    await renderPage({ language: 'en' })
    await user.type(await screen.findByLabelText(/Email/), 'anna@studio.it')
    await user.click(screen.getByRole('button', { name: 'Send the link' }))
    expect(await screen.findByRole('status')).toHaveTextContent('If anna@studio.it belongs to an active account')
  })
})
