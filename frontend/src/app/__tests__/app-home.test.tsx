import { describe, expect, it, vi } from 'vitest'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithIntl } from '@/test/i18n'

const push = vi.fn()

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn(), refresh: vi.fn() }),
}))

vi.mock('next/link', () => ({
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  default: ({ children, href, ...props }: any) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}))

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { name: 'Anna Bianchi' } }),
}))

import AppHome from '../app/page'

describe('the first page after sign-in', () => {
  it('leads with the document check', () => {
    renderWithIntl(<AppHome />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Che cosa controlli oggi, Anna?')
    expect(screen.getByRole('link', { name: 'Controlla un documento' })).toHaveAttribute('href', '/app/controlla')
    expect(screen.queryByText(/Cosa vuoi sapere oggi/)).not.toBeInTheDocument()
  })

  it('gives the document check the first tile', () => {
    renderWithIntl(<AppHome />)
    const tiles = screen
      .getAllByRole('link')
      .filter((link) => link.textContent?.includes('Apri'))
      .map((link) => link.getAttribute('href'))
    expect(tiles).toEqual(['/app/controlla', '/app/ambito', '/app/monitoraggio', '/app/clienti'])
  })

  it('keeps the question box of Chiedi, under its own heading', async () => {
    const user = userEvent.setup()
    renderWithIntl(<AppHome />)
    const ask = screen.getByRole('region', { name: 'Oppure fai una domanda' })
    await user.type(within(ask).getByLabelText('La tua domanda'), 'Che cosa dice l’art. 50?')
    await user.click(within(ask).getByRole('button', { name: 'Invia la domanda' }))
    expect(push).toHaveBeenCalledWith(`/app/chiedi?q=${encodeURIComponent('Che cosa dice l’art. 50?')}`)
  })

  it('reads the same in English', () => {
    renderWithIntl(<AppHome />, { language: 'en' })
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('What are you checking today, Anna?')
    expect(screen.getByRole('link', { name: 'Check a document' })).toHaveAttribute('href', '/app/controlla')
  })
})
