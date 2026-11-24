import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ToastProvider } from '@/components/ui/Toast'
import { ApiError } from '@/lib/api-error'
import type { User } from '@/lib/types'
import { renderWithIntl } from '@/test/i18n'

const mocks = vi.hoisted(() => ({ demo: false, refreshUser: vi.fn() }))

vi.mock('@/lib/api', () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), del: vi.fn() },
}))

vi.mock('@/lib/auth', () => ({
  isDemoMode: () => mocks.demo,
}))

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ refreshUser: mocks.refreshUser }),
}))

import { api } from '@/lib/api'
import { MembersSection } from '../MembersSection'
import { resetDemoMembers } from '../members-api'

const ADMIN: User = {
  id: 'u-anna',
  email: 'anna@studio.example',
  name: 'Anna Bianchi',
  role: 'admin',
  organization_name: 'Studio Esempio',
}

const MEMBERS = [
  {
    id: 'u-anna',
    email: 'anna@studio.example',
    name: 'Anna Bianchi',
    role: 'admin',
    is_active: true,
    email_verified: true,
    created_at: '2026-11-02T09:00:00Z',
  },
  {
    id: 'u-luca',
    email: 'luca@studio.example',
    name: 'Luca Neri',
    role: 'member',
    is_active: true,
    email_verified: true,
    created_at: '2026-11-03T09:00:00Z',
  },
  {
    id: 'u-sara',
    email: 'sara@studio.example',
    name: '',
    role: 'viewer',
    is_active: true,
    email_verified: false,
    created_at: '2026-11-04T09:00:00Z',
  },
]

const LAST_ADMIN =
  "L'organizzazione deve avere almeno un amministratore attivo: nomina prima un altro amministratore."

function failed(status: number, detail: string) {
  return new ApiError('requestFailed', { detail, values: { status: String(status) } })
}

/** GET answers by path: the members, and no invitations yet. */
function serve(members: unknown = MEMBERS) {
  ;(api.get as Mock).mockImplementation(async (path: string) => {
    if (path === '/api/v1/auth/members') {
      if (members instanceof Error) throw members
      return members
    }
    if (path === '/api/v1/auth/invites') return []
    throw new Error(`unexpected GET ${path}`)
  })
}

function renderSection(user: User = ADMIN, { demoMode = false, language = 'it' as 'it' | 'en' } = {}) {
  return renderWithIntl(
    <ToastProvider>
      <MembersSection user={user} demoMode={demoMode} />
    </ToastProvider>,
    { language },
  )
}

async function membersTable() {
  return screen.findByRole('table', { name: 'Membri' })
}

function row(table: HTMLElement, text: string) {
  const found = within(table)
    .getAllByRole('row')
    .find((r) => r.textContent?.includes(text))
  if (!found) throw new Error(`no row with ${text}`)
  return found
}

describe('MembersSection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.demo = false
    serve()
  })

  it('lists every member with name, email, role and state', async () => {
    renderSection()
    const table = await membersTable()
    expect(api.get).toHaveBeenCalledWith('/api/v1/auth/members')

    const anna = row(table, 'anna@studio.example')
    expect(anna).toHaveTextContent('Anna Bianchi')
    expect(within(anna).getByText('Tu')).toBeInTheDocument()
    expect(within(anna).getByRole('combobox', { name: 'Ruolo di Anna Bianchi' })).toHaveValue('admin')
    expect(within(anna).getByText('Attivo')).toBeInTheDocument()
    // Your own account is not removed from the list.
    expect(within(anna).queryByRole('button', { name: /Rimuovi/ })).not.toBeInTheDocument()

    const luca = row(table, 'luca@studio.example')
    expect(within(luca).getByRole('combobox', { name: 'Ruolo di Luca Neri' })).toHaveValue('member')
    expect(within(luca).getByRole('button', { name: 'Rimuovi Luca Neri' })).toBeInTheDocument()

    // No name: the email stands in for it.
    const sara = row(table, 'sara@studio.example')
    expect(within(sara).getByRole('combobox', { name: 'Ruolo di sara@studio.example' })).toHaveValue('viewer')
    expect(within(sara).getByText('Email da confermare')).toBeInTheDocument()
    expect(within(sara).getByRole('option', { name: 'Lettore' })).toBeInTheDocument()

    expect(screen.getByText(/Il tuo account non si rimuove da qui/)).toBeInTheDocument()
    expect(screen.getByText('Che cosa fa ogni ruolo')).toBeInTheDocument()
  })

  it('offers the invitations next to the members', async () => {
    const user = userEvent.setup()
    ;(api.post as Mock).mockResolvedValue({
      id: 'inv-1',
      code: 'ABCD2345',
      email: 'nuovo@studio.example',
      organization_id: 'org-1',
      role: 'member',
      status: 'pending',
      created_at: '2026-11-24T10:00:00Z',
      expires_at: '2026-12-08T10:00:00Z',
      used_at: null,
    })
    renderSection()
    await membersTable()
    expect(screen.getByRole('heading', { name: 'Inviti' })).toBeInTheDocument()

    await user.type(screen.getByRole('textbox', { name: /Email/ }), 'nuovo@studio.example')
    await user.click(screen.getByRole('button', { name: /Crea l.invito/ }))
    expect(api.post).toHaveBeenCalledWith('/api/v1/auth/invites', { email: 'nuovo@studio.example', role: 'member' })
    expect(await screen.findByText('ABCD2345')).toBeInTheDocument()
  })

  it('changes the role of another member at once', async () => {
    const user = userEvent.setup()
    ;(api.patch as Mock).mockResolvedValue({ ...MEMBERS[1], role: 'viewer' })
    renderSection()
    const table = await membersTable()

    await user.selectOptions(within(table).getByRole('combobox', { name: 'Ruolo di Luca Neri' }), 'viewer')
    expect(api.patch).toHaveBeenCalledWith('/api/v1/auth/members/u-luca', { role: 'viewer' })
    expect(await screen.findByText('Luca Neri ora ha il ruolo Lettore.')).toBeInTheDocument()
    expect(within(table).getByRole('combobox', { name: 'Ruolo di Luca Neri' })).toHaveValue('viewer')
  })

  it('shows the server’s reason when a role does not change, and keeps the old one', async () => {
    const user = userEvent.setup()
    ;(api.patch as Mock).mockRejectedValue(failed(403, "Operazione riservata agli amministratori dell'organizzazione."))
    renderSection()
    const table = await membersTable()

    await user.selectOptions(within(table).getByRole('combobox', { name: 'Ruolo di Luca Neri' }), 'admin')
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Il ruolo di Luca Neri non è cambiato')
    expect(alert).toHaveTextContent("Operazione riservata agli amministratori dell'organizzazione.")
    expect(within(table).getByRole('combobox', { name: 'Ruolo di Luca Neri' })).toHaveValue('member')
  })

  it('drops from the list a member the server no longer has', async () => {
    const user = userEvent.setup()
    ;(api.patch as Mock).mockRejectedValue(failed(404, 'Membro non trovato.'))
    renderSection()
    const table = await membersTable()

    await user.selectOptions(within(table).getByRole('combobox', { name: 'Ruolo di Luca Neri' }), 'viewer')
    expect(await screen.findByRole('alert')).toHaveTextContent('Membro non trovato.')
    expect(within(table).queryByText('luca@studio.example')).not.toBeInTheDocument()
  })

  it('removes a member only after a confirmation that says what is lost', async () => {
    const user = userEvent.setup()
    ;(api.del as Mock).mockResolvedValue(undefined)
    renderSection()
    const table = await membersTable()

    await user.click(within(table).getByRole('button', { name: 'Rimuovi Luca Neri' }))
    let dialog = screen.getByRole('dialog')
    expect(within(dialog).getByRole('heading', { name: 'Rimuovere Luca Neri?' })).toBeInTheDocument()
    expect(dialog).toHaveTextContent('luca@studio.example')
    expect(dialog).toHaveTextContent('Si perdono l’account e le sue conversazioni nella pagina Chiedi')
    expect(dialog).toHaveTextContent('Restano all’organizzazione clienti, controlli, report e inviti')
    expect(dialog).toHaveTextContent('Non si può annullare')

    await user.click(within(dialog).getByRole('button', { name: 'Annulla' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(api.del).not.toHaveBeenCalled()

    await user.click(within(table).getByRole('button', { name: 'Rimuovi Luca Neri' }))
    dialog = screen.getByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Rimuovi dall’organizzazione' }))
    await waitFor(() => expect(api.del).toHaveBeenCalledWith('/api/v1/auth/members/u-luca'))
    expect(await screen.findByText('Luca Neri non fa più parte dell’organizzazione.')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(within(table).queryByText('luca@studio.example')).not.toBeInTheDocument()
  })

  it('keeps the removal dialog open with the server’s reason when it fails', async () => {
    const user = userEvent.setup()
    ;(api.del as Mock).mockRejectedValue(failed(409, LAST_ADMIN))
    renderSection()
    const table = await membersTable()

    await user.click(within(table).getByRole('button', { name: 'Rimuovi Luca Neri' }))
    const dialog = screen.getByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Rimuovi dall’organizzazione' }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent(LAST_ADMIN)
    expect(within(table).getByText('luca@studio.example')).toBeInTheDocument()
  })

  it('asks before an admin gives up the role, and shows the refusal for the last admin', async () => {
    const user = userEvent.setup()
    ;(api.patch as Mock).mockRejectedValue(failed(409, LAST_ADMIN))
    renderSection()
    const table = await membersTable()

    await user.selectOptions(within(table).getByRole('combobox', { name: 'Ruolo di Anna Bianchi' }), 'member')
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByRole('heading', { name: 'Lasciare il ruolo di amministratore?' })).toBeInTheDocument()
    expect(dialog).toHaveTextContent('Con il ruolo Membro non potrai più gestire membri e inviti.')
    expect(api.patch).not.toHaveBeenCalled()

    await user.click(within(dialog).getByRole('button', { name: 'Cambia il mio ruolo' }))
    expect(api.patch).toHaveBeenCalledWith('/api/v1/auth/members/u-anna', { role: 'member' })
    expect(await within(dialog).findByRole('alert')).toHaveTextContent(LAST_ADMIN)
    expect(mocks.refreshUser).not.toHaveBeenCalled()

    await user.click(within(dialog).getByRole('button', { name: 'Annulla' }))
    expect(within(table).getByRole('combobox', { name: 'Ruolo di Anna Bianchi' })).toHaveValue('admin')
  })

  it('hands over to the note once the admin has given up the role', async () => {
    const user = userEvent.setup()
    ;(api.patch as Mock).mockResolvedValue({ ...MEMBERS[0], role: 'viewer' })
    renderSection()
    const table = await membersTable()

    await user.selectOptions(within(table).getByRole('combobox', { name: 'Ruolo di Anna Bianchi' }), 'viewer')
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cambia il mio ruolo' }))

    expect(await screen.findByText(/Solo gli amministratori vedono e gestiscono i membri/)).toBeInTheDocument()
    expect(screen.queryByRole('table', { name: 'Membri' })).not.toBeInTheDocument()
    expect(screen.getByText('Il tuo ruolo ora è Lettore')).toBeInTheDocument()
    expect(mocks.refreshUser).toHaveBeenCalledTimes(1)
  })

  it('shows the other roles a note and asks the server nothing', () => {
    renderSection({ ...ADMIN, role: 'member' })
    expect(screen.getByText(/Solo gli amministratori vedono e gestiscono i membri/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Crea l.invito/ })).not.toBeInTheDocument()
    expect(api.get).not.toHaveBeenCalled()
  })

  it('says so when the server has no member list yet', async () => {
    serve(failed(404, 'Not Found'))
    renderSection()
    expect(await screen.findByText('La gestione dei membri non è ancora attiva su questo server')).toBeInTheDocument()
    expect(screen.getByText(/endpoint \/api\/v1\/auth\/members non trovato/)).toBeInTheDocument()
  })

  it('shows why the list did not load and loads it again on request', async () => {
    const user = userEvent.setup()
    serve(failed(403, "Conferma l'indirizzo email per usare NormaAI."))
    renderSection()
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('I membri non si sono caricati')
    expect(alert).toHaveTextContent("Conferma l'indirizzo email per usare NormaAI.")

    serve()
    await user.click(within(alert).getByRole('button', { name: 'Riprova il caricamento' }))
    expect(await membersTable()).toBeInTheDocument()
  })

  it('in the demo shows example members and keeps the demo account an admin', async () => {
    mocks.demo = true
    resetDemoMembers()
    renderSection({ ...ADMIN, id: 'demo-user-001' }, { demoMode: true })
    const table = await membersTable()
    expect(screen.getByText(/Nella demo i membri sono esempi/)).toBeInTheDocument()
    expect(within(table).getAllByRole('row')).toHaveLength(4)
    const own = row(table, 'giulia@studio-esempio.example')
    expect(within(own).getByText('Tu')).toBeInTheDocument()
    expect(within(own).getByRole('combobox')).toBeDisabled()
    expect(api.get).not.toHaveBeenCalledWith('/api/v1/auth/members')
  })

  it('speaks English too', async () => {
    renderSection(ADMIN, { language: 'en' })
    const table = await screen.findByRole('table', { name: 'Members' })
    expect(within(table).getByRole('button', { name: 'Remove Luca Neri' })).toBeInTheDocument()
    expect(within(row(table, 'sara@studio.example')).getByText('Email not confirmed')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Invitations' })).toBeInTheDocument()
  })
})
