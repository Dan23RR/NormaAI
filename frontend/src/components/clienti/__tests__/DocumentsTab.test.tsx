import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithIntl } from '@/test/i18n'
import { ApiError } from '@/lib/api-error'
import { DEMO_CLIENTS } from '@/lib/mock-data'
import { demoDocumentsRoute, resetDemoDocuments } from '@/lib/mock-documents'
import type { Client } from '@/lib/types'

const mocks = vi.hoisted(() => ({ get: vi.fn(), upload: vi.fn() }))

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  usePathname: () => '/app/clienti/demo-c2',
}))

vi.mock('next/link', () => ({
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  default: ({ children, href, ...props }: any) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}))

vi.mock('@/lib/api', () => ({ api: { get: mocks.get, upload: mocks.upload } }))

import { DocumentsTab } from '../DocumentsTab'

const client = (id: string): Client => ({ org_id: 'demo-org', ...(DEMO_CLIENTS.find((c) => c.id === id) as Omit<Client, 'org_id'>) })

describe('DocumentsTab (the documents checked for a client)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    resetDemoDocuments()
    mocks.get.mockImplementation(async (path: string) => {
      const answer = demoDocumentsRoute('GET', path)
      if (answer.handled) return answer.value
      throw new Error(`unexpected GET ${path}`)
    })
  })

  it('lists only the checks of this client and links to a new check with the client chosen', async () => {
    renderWithIntl(<DocumentsTab client={client('demo-c2')} />)
    expect(screen.getByRole('heading', { name: 'Documenti controllati' })).toBeInTheDocument()
    expect(screen.getByText(/I documenti di Beta Software S\.r\.l\. di cui hai controllato i riferimenti di legge\./)).toBeInTheDocument()

    const table = await screen.findByRole('table')
    expect(mocks.get).toHaveBeenCalledWith('/api/v1/documents/checks?client_id=demo-c2&limit=50&offset=0')
    expect(within(table).getAllByRole('row')).toHaveLength(2)
    expect(within(table).getByRole('link', { name: 'Procedura violazioni dati personali.docx' })).toHaveAttribute(
      'href',
      '/app/controlla/demo-doc-gdpr',
    )
    expect(within(table).getByText('Da correggere')).toBeInTheDocument()
    // Every row is of this client: the column is not repeated.
    expect(within(table).queryByRole('columnheader', { name: 'Cliente' })).not.toBeInTheDocument()
    expect(screen.queryByText('Policy uso IA.pdf')).not.toBeInTheDocument()

    expect(screen.getByRole('link', { name: 'Controlla un documento per questo cliente' })).toHaveAttribute(
      'href',
      '/app/controlla?cliente=demo-c2',
    )
  })

  it('shows a check to review as such', async () => {
    renderWithIntl(<DocumentsTab client={client('demo-c6')} />)
    const table = await screen.findByRole('table')
    expect(within(table).getByText('Da rivedere')).toBeInTheDocument()
    expect(within(table).getByText('una norma citata è cambiata')).toBeInTheDocument()
  })

  it('invites to the first check when the client has none', async () => {
    renderWithIntl(<DocumentsTab client={client('demo-c4')} />)
    expect(await screen.findByText('Nessun documento controllato per questo cliente')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    // One way to the check, not two.
    expect(screen.getAllByRole('link', { name: 'Controlla un documento per questo cliente' })).toHaveLength(1)
    expect(screen.getByRole('link', { name: 'Controlla un documento per questo cliente' })).toHaveAttribute(
      'href',
      '/app/controlla?cliente=demo-c4',
    )
  })

  it('no longer uploads anything to the index of the organisation', async () => {
    renderWithIntl(<DocumentsTab client={client('demo-c2')} />)
    await screen.findByRole('table')
    expect(screen.queryByLabelText(/File/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Carica/ })).not.toBeInTheDocument()
    expect(mocks.upload).not.toHaveBeenCalled()
  })

  it('says when the checks did not load and tries again', async () => {
    const user = userEvent.setup()
    mocks.get.mockRejectedValueOnce(new ApiError('requestFailed', { values: { status: '503' } }))
    renderWithIntl(<DocumentsTab client={client('demo-c2')} />)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('I documenti controllati non si sono caricati')
    expect(alert).toHaveTextContent('Codice 503')
    await user.click(within(alert).getByRole('button', { name: 'Riprova il caricamento' }))
    expect(await screen.findByRole('table')).toBeInTheDocument()
  })

  it('says when it shows only the most recent checks', async () => {
    mocks.get.mockImplementation(async (path: string) => {
      const answer = demoDocumentsRoute('GET', path)
      const list = (answer as { value: { items: unknown[] } }).value
      return { items: list.items, total: 73 }
    })
    renderWithIntl(<DocumentsTab client={client('demo-c2')} />, { language: 'en' })
    expect(await screen.findByText('The 1 most recent checks out of 73 are shown.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Check a document for this client' })).toBeInTheDocument()
  })
})
