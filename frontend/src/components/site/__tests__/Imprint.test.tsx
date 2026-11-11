import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, screen } from '@testing-library/react'
import { renderWithIntl } from '@/test/i18n'

// The VAT number is read once, when the module loads (it is inlined at build
// time in production), so each case imports a fresh copy of the component.
async function renderImprint(language: 'it' | 'en' = 'it') {
  vi.resetModules()
  const { Imprint } = await import('../Imprint')
  return renderWithIntl(<Imprint />, { language })
}

describe('Imprint', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllEnvs()
  })

  it('states who runs NormaAI and how to reach them', async () => {
    vi.stubEnv('NEXT_PUBLIC_VAT_NUMBER', '')
    await renderImprint()
    expect(
      screen.getByText(
        'NormaAI è un progetto di Daniel Culotta, persona fisica, Inverigo (CO), Italia, non ancora costituito in società.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'info@normaai.org' })).toHaveAttribute('href', 'mailto:info@normaai.org')
  })

  it('shows no VAT line when no VAT number is configured', async () => {
    vi.stubEnv('NEXT_PUBLIC_VAT_NUMBER', '')
    await renderImprint()
    expect(screen.queryByText(/Partita IVA/)).not.toBeInTheDocument()
  })

  it('shows the configured VAT number, and only that', async () => {
    vi.stubEnv('NEXT_PUBLIC_VAT_NUMBER', ' IT00000000000 ')
    await renderImprint()
    expect(screen.getByText('Partita IVA: IT00000000000')).toBeInTheDocument()
  })

  it('speaks English when the interface does', async () => {
    vi.stubEnv('NEXT_PUBLIC_VAT_NUMBER', 'IT00000000000')
    await renderImprint('en')
    expect(
      screen.getByText('NormaAI is a project of Daniel Culotta, natural person, Inverigo (CO), Italy, not yet incorporated.'),
    ).toBeInTheDocument()
    expect(screen.getByText('VAT number: IT00000000000')).toBeInTheDocument()
  })
})
