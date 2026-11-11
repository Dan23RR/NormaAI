import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithIntl } from '@/test/i18n'
import NotFound from '../not-found'

vi.mock('next/link', () => ({
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  default: ({ children, href, ...props }: any) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}))

// The header only asks whether a session exists.
vi.mock('@/lib/auth', () => ({ getAccessToken: () => null }))

describe('not-found page', () => {
  it('says the page does not exist and offers the ones that do', () => {
    renderWithIntl(<NotFound />)
    expect(screen.getByRole('heading', { level: 1, name: 'Pagina non trovata' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Vai alla pagina principale' })).toHaveAttribute('href', '/')
    const main = screen.getByRole('main')
    const hrefs = Array.from(main.querySelectorAll('a')).map((a) => a.getAttribute('href'))
    expect(hrefs).toEqual(['/', '/scope-csrd.html', '/scope-aiact.html', '/metodo'])
  })

  it('carries the footer with who runs the site', () => {
    renderWithIntl(<NotFound />)
    expect(screen.getByRole('contentinfo')).toHaveTextContent(
      'NormaAI è un progetto di Daniel Culotta, persona fisica, Inverigo (CO), Italia, non ancora costituito in società.',
    )
  })

  it('speaks English when the interface does', () => {
    renderWithIntl(<NotFound />, { language: 'en' })
    expect(screen.getByRole('heading', { level: 1, name: 'Page not found' })).toBeInTheDocument()
  })
})
