import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ToastProvider } from '@/components/ui/Toast'
import { InvitesSection } from '../InvitesSection'

vi.mock('@/lib/api', () => ({
  api: { get: vi.fn(), post: vi.fn() },
}))

vi.mock('@/lib/auth', () => ({
  isDemoMode: () => false,
}))

import { api } from '@/lib/api'

function renderSection() {
  return render(
    <ToastProvider>
      <InvitesSection demoMode={false} />
    </ToastProvider>,
  )
}

describe('InvitesSection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    ;(api.get as Mock).mockResolvedValue([])
    ;(api.post as Mock).mockResolvedValue({
      code: 'ABCD2345',
      email: 'anna@azienda.it',
      expires_at: '2026-11-01T10:00:00Z',
    })
  })

  it('asks for a valid email before calling the API', async () => {
    const user = userEvent.setup()
    renderSection()
    expect(await screen.findByText('Nessun invito ancora')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Crea l.invito/ }))
    expect(screen.getByText('Inserisci l’email della persona da invitare.')).toBeInTheDocument()

    await user.type(screen.getByLabelText(/Email/), 'anna@azienda')
    await user.click(screen.getByRole('button', { name: /Crea l.invito/ }))
    expect(screen.getByText(/L’email non sembra valida/)).toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('creates an invite, shows the code and reloads the list', async () => {
    const user = userEvent.setup()
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    ;(api.get as Mock)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        {
          code: 'ABCD2345',
          email: 'anna@azienda.it',
          organization_id: 'org-1',
          used: false,
          expires_at: '2026-11-01T10:00:00Z',
          created_at: '2026-10-23T10:00:00Z',
        },
      ])

    renderSection()
    await screen.findByText('Nessun invito ancora')

    await user.type(screen.getByLabelText(/Email/), 'anna@azienda.it')
    await user.click(screen.getByRole('button', { name: /Crea l.invito/ }))

    expect(api.post).toHaveBeenCalledWith('/api/v1/auth/invites', { email: 'anna@azienda.it' })
    expect(await screen.findByText('Invito creato per anna@azienda.it')).toBeInTheDocument()
    expect(screen.getAllByText('ABCD2345').length).toBeGreaterThan(0)
    expect(api.get).toHaveBeenCalledTimes(2)

    const table = await screen.findByRole('table')
    expect(within(table).getByText('anna@azienda.it')).toBeInTheDocument()
    expect(within(table).getByText('Attivo')).toBeInTheDocument()
    expect(within(table).getByText('2026-11-01')).toBeInTheDocument()

    await user.click(screen.getAllByRole('button', { name: 'Copia il codice' })[0])
    expect(writeText).toHaveBeenCalledWith('ABCD2345')
    expect(await screen.findByText('Codice copiato')).toBeInTheDocument()
  })

  it('explains when the backend does not have invitations yet', async () => {
    ;(api.get as Mock).mockRejectedValue(new Error('Not Found'))
    renderSection()
    expect(await screen.findByText('Gli inviti non sono ancora attivi su questo server')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Crea l.invito/ })).not.toBeInTheDocument()
  })
})
