import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ToastProvider } from '@/components/ui/Toast'
import { DEMO_CLIENTS } from '@/lib/mock-data'
import ClientiPage from '@/app/app/clienti/page'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/app/clienti',
  useParams: () => ({}),
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
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), del: vi.fn() },
}))

import { api } from '@/lib/api'

function renderPage() {
  return render(
    <ToastProvider>
      <ClientiPage />
    </ToastProvider>,
  )
}

describe('ClientiPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    ;(api.get as Mock).mockResolvedValue({ data: DEMO_CLIENTS, clients: DEMO_CLIENTS, total: DEMO_CLIENTS.length })
  })

  it('renders the demo clients with Italian thousands separators and framework badges', async () => {
    renderPage()
    expect(await screen.findByText('EnergiePlus GmbH')).toBeInTheDocument()
    for (const client of DEMO_CLIENTS) {
      expect(screen.getByText(client.name)).toBeInTheDocument()
    }
    const table = screen.getByRole('table')
    // Node may ship a small ICU: the separator is "." with full Italian locale data, "," without.
    expect(within(table).getByText(/^5[.,]000$/)).toBeInTheDocument()
    expect(within(table).getAllByText('CSRD').length).toBeGreaterThan(0)
    expect(within(table).getByText('2026-03-02')).toBeInTheDocument()
    expect(screen.getByText('4 clienti')).toBeInTheDocument()
  })

  it('filters by name or sector and offers to clear an empty search', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('EnergiePlus GmbH')
    const search = screen.getByLabelText('Cerca tra i clienti')
    await user.type(search, 'banca')
    expect(screen.getByText('Banca Meridiana S.p.A.')).toBeInTheDocument()
    expect(screen.queryByText('EnergiePlus GmbH')).not.toBeInTheDocument()
    expect(screen.getByText('1 di 4 clienti')).toBeInTheDocument()

    await user.clear(search)
    await user.type(search, 'zzz')
    expect(screen.getByText(/Nessun cliente corrisponde a «zzz»/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Cancella la ricerca' }))
    expect(screen.getByText('EnergiePlus GmbH')).toBeInTheDocument()
  })

  it('validates the new client form in Italian before calling the API', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('EnergiePlus GmbH')

    await user.click(screen.getByRole('button', { name: 'Nuovo cliente' }))
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText('Nuovo cliente')).toBeInTheDocument()

    await user.click(within(dialog).getByRole('button', { name: 'Crea il cliente' }))
    expect(await within(dialog).findByText('Inserisci il nome del cliente.')).toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalled()

    await user.type(within(dialog).getByLabelText(/Nome del cliente/), 'Nuova S.r.l.')
    await user.type(within(dialog).getByLabelText('Dipendenti'), 'dodici')
    await user.type(within(dialog).getByLabelText(/Paesi in cui opera/), 'IT, Italia')
    await user.click(within(dialog).getByRole('button', { name: 'Crea il cliente' }))
    expect(await within(dialog).findByText('Inserisci il numero di dipendenti come intero, zero o più.')).toBeInTheDocument()
    expect(within(dialog).getByText(/Non validi: ITALIA\./)).toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('creates a client and adds it to the list', async () => {
    const user = userEvent.setup()
    ;(api.post as Mock).mockResolvedValue({
      id: 'new-1',
      org_id: 'org',
      name: 'Nuova S.r.l.',
      sector: 'Servizi',
      employee_count: 12,
      revenue_eur: 1500000,
      jurisdictions: ['IT'],
      applicable_frameworks: ['GDPR'],
      created_at: '2026-10-23T10:00:00Z',
      updated_at: '2026-10-23T10:00:00Z',
    })
    renderPage()
    await screen.findByText('EnergiePlus GmbH')

    await user.click(screen.getByRole('button', { name: 'Nuovo cliente' }))
    const dialog = screen.getByRole('dialog')
    await user.type(within(dialog).getByLabelText(/Nome del cliente/), 'Nuova S.r.l.')
    await user.type(within(dialog).getByLabelText('Settore'), 'Servizi')
    await user.type(within(dialog).getByLabelText('Dipendenti'), '12')
    await user.type(within(dialog).getByLabelText(/Fatturato annuo/), '1500000')
    await user.type(within(dialog).getByLabelText(/Paesi in cui opera/), 'it')
    await user.click(within(dialog).getByLabelText('GDPR'))
    await user.click(within(dialog).getByRole('button', { name: 'Crea il cliente' }))

    expect(api.post).toHaveBeenCalledWith('/api/v1/clients', {
      name: 'Nuova S.r.l.',
      sector: 'Servizi',
      employee_count: 12,
      revenue_eur: 1500000,
      jurisdictions: ['IT'],
      applicable_frameworks: ['GDPR'],
    })
    expect(await screen.findByText('Cliente creato')).toBeInTheDocument()
    const table = screen.getByRole('table')
    expect(within(table).getByText('Nuova S.r.l.')).toBeInTheDocument()
    expect(screen.getByText('5 clienti')).toBeInTheDocument()
  })
})
