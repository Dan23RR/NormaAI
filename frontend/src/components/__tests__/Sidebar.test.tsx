import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import Sidebar from '../Sidebar'

// Mock next modules
vi.mock('next/navigation', () => ({
  usePathname: () => '/dashboard',
}))

vi.mock('next/link', () => ({
  default: ({ children, href, ...props }: any) => (
    <a href={href} {...props}>{children}</a>
  ),
}))

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({
    user: { id: '1', email: 'test@test.com', name: 'Test User', role: 'admin', organization_name: 'Test Org' },
    loading: false,
    demoMode: true,
    login: vi.fn(),
    register: vi.fn(),
    loginDemo: vi.fn(),
    logout: vi.fn(),
  }),
}))

const defaultProps = {
  collapsed: false,
  onToggle: vi.fn(),
  mobileOpen: false,
  onMobileClose: vi.fn(),
}

describe('Sidebar', () => {
  it('renders all nav items for admin user', () => {
    render(<Sidebar {...defaultProps} />)

    expect(screen.getAllByText('Overview').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Q&A').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Gap Analysis').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Monitor').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Alerts').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Documents').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Reports').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Clients').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Audit Trail').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Workflow').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Analytics').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Admin').length).toBeGreaterThanOrEqual(1)
  })

  it('applies active class to current page link', () => {
    render(<Sidebar {...defaultProps} />)

    // The Overview link at /dashboard should have aria-current="page"
    const activeLinks = screen.getAllByRole('link', { current: 'page' })
    expect(activeLinks.length).toBeGreaterThanOrEqual(1)
    expect(activeLinks[0]).toHaveClass('bg-accent/10')
  })

  it('displays knowledge base metadata', () => {
    render(<Sidebar {...defaultProps} />)

    expect(screen.getAllByText('Knowledge Base').length).toBeGreaterThanOrEqual(1)
    // chunks count may use locale-specific separators (14,823 or 14.823)
    expect(screen.getAllByText(/14[.,]823 chunks/i).length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText(/7 framework EU/i).length).toBeGreaterThanOrEqual(1)
  })

  it('hides labels when collapsed', () => {
    render(<Sidebar {...defaultProps} collapsed={true} />)

    // In collapsed mode, the text "NormaAI" should not appear
    expect(screen.queryByText('NormaAI')).not.toBeInTheDocument()
    // Nav item labels should not appear as text nodes
    expect(screen.queryByText('Overview')).not.toBeInTheDocument()
  })

  it('shows demo mode badge when expanded', () => {
    render(<Sidebar {...defaultProps} />)

    expect(screen.getAllByText('Demo Mode').length).toBeGreaterThanOrEqual(1)
  })
})
