import { describe, it, expect, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import AuditTrailPage from '../page'

// Mock next/navigation
vi.mock('next/navigation', () => ({
  usePathname: () => '/dashboard/audit-trail',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useParams: () => ({}),
}))

describe('AuditTrailPage', () => {
  it('renders all audit events in the table', () => {
    render(<AuditTrailPage />)

    // The page should show the title
    expect(screen.getByText('Audit Trail')).toBeInTheDocument()

    // Should show event count
    const countText = screen.getByText(/eventi/i)
    expect(countText).toBeInTheDocument()

    // Should have table rows (user names from demo data)
    expect(screen.getAllByText('Demo User').length).toBeGreaterThan(0)
  })

  it('filters by resource type', async () => {
    const user = userEvent.setup()
    render(<AuditTrailPage />)

    // Find the resource type select (has "Tutte le risorse" default)
    const resourceSelect = screen.getByDisplayValue('Tutte le risorse')
    await user.selectOptions(resourceSelect, 'qa')

    // Count text should now show "filtrati da"
    expect(screen.getByText(/filtrati da/)).toBeInTheDocument()
  })

  it('filters by framework', async () => {
    const user = userEvent.setup()
    render(<AuditTrailPage />)

    const frameworkSelect = screen.getByDisplayValue('Tutti i framework')
    await user.selectOptions(frameworkSelect, 'CSRD')

    // Should still show some events (CSRD events exist in demo data)
    expect(screen.getByText(/eventi/)).toBeInTheDocument()
  })

  it('filters by search text', async () => {
    const user = userEvent.setup()
    render(<AuditTrailPage />)

    const searchInput = screen.getByPlaceholderText(/Cerca per utente/i)
    await user.type(searchInput, 'CSRD')

    // Should show filtered results
    expect(screen.getByText(/eventi/)).toBeInTheDocument()
  })

  it('has CSV export button', () => {
    render(<AuditTrailPage />)

    const exportBtn = screen.getByText(/Esporta CSV/i)
    expect(exportBtn).toBeInTheDocument()
  })

  it('CSV export creates a valid download', async () => {
    const user = userEvent.setup()
    render(<AuditTrailPage />)

    // Mock URL.createObjectURL and document.createElement
    const mockUrl = 'blob:test'
    const revokeObjectURL = vi.fn()
    const createObjectURL = vi.fn(() => mockUrl)
    const clickFn = vi.fn()

    vi.stubGlobal('URL', { createObjectURL, revokeObjectURL })

    const origCreateElement = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      if (tag === 'a') {
        const el = origCreateElement('a')
        el.click = clickFn
        return el
      }
      return origCreateElement(tag)
    })

    const exportBtn = screen.getByText(/Esporta CSV/i)
    await user.click(exportBtn)

    expect(createObjectURL).toHaveBeenCalled()
    expect(clickFn).toHaveBeenCalled()
    expect(revokeObjectURL).toHaveBeenCalledWith(mockUrl)

    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })
})
