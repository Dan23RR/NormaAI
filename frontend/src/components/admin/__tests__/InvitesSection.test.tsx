import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ToastProvider } from '@/components/ui/Toast'
import { renderWithIntl } from '@/test/i18n'
import { InvitesSection } from '../InvitesSection'

vi.mock('@/lib/api', () => ({
  api: { get: vi.fn(), post: vi.fn() },
}))

vi.mock('@/lib/auth', () => ({
  isDemoMode: () => false,
}))

import { api } from '@/lib/api'

const CREATED = {
  id: 'inv-1',
  code: 'ABCD2345',
  email: 'anna@azienda.it',
  organization_id: 'org-1',
  role: 'member',
  status: 'pending',
  created_at: '2026-10-23T10:00:00Z',
  expires_at: '2026-11-01T10:00:00Z',
  used_at: null,
}

function renderSection(language: 'it' | 'en' = 'it') {
  return renderWithIntl(
    <ToastProvider>
      <InvitesSection demoMode={false} />
    </ToastProvider>,
    { language },
  )
}

describe('InvitesSection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    ;(api.get as Mock).mockResolvedValue([])
    ;(api.post as Mock).mockResolvedValue(CREATED)
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

  it('creates an invite with a role, shows the code once and reloads the list', async () => {
    const user = userEvent.setup()
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    const { code: _code, ...listed } = CREATED
    void _code
    ;(api.get as Mock).mockResolvedValueOnce([]).mockResolvedValueOnce([listed])

    renderSection()
    await screen.findByText('Nessun invito ancora')

    await user.type(screen.getByLabelText(/Email/), 'anna@azienda.it')
    await user.selectOptions(screen.getByLabelText(/Ruolo/), 'viewer')
    await user.click(screen.getByRole('button', { name: /Crea l.invito/ }))

    expect(api.post).toHaveBeenCalledWith('/api/v1/auth/invites', { email: 'anna@azienda.it', role: 'viewer' })
    expect(await screen.findByText('Invito creato per anna@azienda.it')).toBeInTheDocument()
    expect(screen.getByText('ABCD2345')).toBeInTheDocument()
    expect(api.get).toHaveBeenCalledTimes(2)

    const table = await screen.findByRole('table')
    expect(within(table).getByText('anna@azienda.it')).toBeInTheDocument()
    expect(within(table).getByText('Membro')).toBeInTheDocument()
    expect(within(table).getByText('Attivo')).toBeInTheDocument()
    expect(within(table).getByText('2026-11-01')).toBeInTheDocument()
    expect(within(table).queryByText('ABCD2345')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Copia il codice' }))
    expect(writeText).toHaveBeenCalledWith('ABCD2345')
    expect(await screen.findByText('Codice copiato')).toBeInTheDocument()
  })

  it('shows used and expired invitations as such', async () => {
    ;(api.get as Mock).mockResolvedValue([
      { ...CREATED, id: 'inv-2', email: 'usato@azienda.it', status: 'used', used_at: '2026-10-24T09:00:00Z' },
      { ...CREATED, id: 'inv-3', email: 'scaduto@azienda.it', status: 'expired' },
    ])
    renderSection()
    const table = await screen.findByRole('table')
    expect(within(table).getByText('Usato')).toBeInTheDocument()
    expect(within(table).getByText('Scaduto')).toBeInTheDocument()
  })

  it('explains when the backend does not have invitations yet', async () => {
    ;(api.get as Mock).mockRejectedValue(new Error('Not Found'))
    renderSection()
    expect(await screen.findByText('Gli inviti non sono ancora attivi su questo server')).toBeInTheDocument()
    expect(screen.getByText(/endpoint \/api\/v1\/auth\/invites non trovato/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Crea l.invito/ })).not.toBeInTheDocument()
  })

  it('says the same in English', async () => {
    ;(api.get as Mock).mockRejectedValue(new Error('Not Found'))
    renderSection('en')
    expect(await screen.findByText('Invitations are not active on this server yet')).toBeInTheDocument()
    expect(screen.getByText(/endpoint \/api\/v1\/auth\/invites not found/)).toBeInTheDocument()
  })
})
