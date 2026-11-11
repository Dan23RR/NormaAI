import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithIntl } from '@/test/i18n'
import { DEMO_CLIENTS, getMockGapAnalysis } from '@/lib/mock-data'
import type { Client, CompanyProfile } from '@/lib/types'

const mocks = vi.hoisted(() => ({ post: vi.fn() }))

vi.mock('@/lib/api', () => ({ api: { post: mocks.post } }))

import { ComplianceTab } from '../ComplianceTab'

const client = (id: string): Client => ({ org_id: 'demo-org', ...(DEMO_CLIENTS.find((c) => c.id === id) as Omit<Client, 'org_id'>) })

describe('ComplianceTab (the requirements of a framework, to check)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorage.clear()
    mocks.post.mockImplementation(async (_path: string, body: { framework: string; company_profile: CompanyProfile }) => ({
      data: getMockGapAnalysis(body.framework, body.company_profile),
    }))
  })

  it('lists the requirements with their articles, each to check, and gives no score or verdict', async () => {
    const user = userEvent.setup()
    renderWithIntl(<ComplianceTab client={client('demo-c1')} />)
    await user.click(screen.getByRole('button', { name: 'Elenca i requisiti' }))

    expect(await screen.findByRole('heading', { name: /Requisiti .* da verificare/ })).toBeInTheDocument()
    expect(screen.getByText(/Qui non viene esaminato nessun documento del cliente/)).toBeInTheDocument()
    // No document is sent with the profile.
    const [path, body] = mocks.post.mock.calls[0]
    expect(path).toBe('/api/v1/gap-analysis')
    expect(body.company_profile.existing_documents).toBe('')

    const table = screen.getByRole('table')
    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows.length).toBeGreaterThan(0)
    for (const row of rows) {
      expect(within(row).getByText(/^(Da verificare|Non applicabile al profilo)$/)).toBeInTheDocument()
    }
    expect(within(table).getAllByText('Da verificare').length).toBeGreaterThan(0)
    // Nothing that reads as an assessment made on missing evidence.
    expect(screen.queryByText(/Non conforme|Conforme|Conformità parziale|Buon livello di conformità|Parzialmente/)).not.toBeInTheDocument()
    expect(screen.queryByText(/%/)).not.toBeInTheDocument()
    expect(screen.queryByText('Raccomandazioni principali')).not.toBeInTheDocument()
  })

  it('says the same in English', async () => {
    const user = userEvent.setup()
    renderWithIntl(<ComplianceTab client={client('demo-c1')} />, { language: 'en' })
    await user.click(screen.getByRole('button', { name: 'List the requirements' }))
    expect(await screen.findByText(/No document of the client is examined here/)).toBeInTheDocument()
    expect(within(screen.getByRole('table')).getAllByText('To check').length).toBeGreaterThan(0)
    expect(screen.queryByText(/Non-compliant|Compliant/)).not.toBeInTheDocument()
  })
})
