import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithIntl } from '@/test/i18n'
import { DeadlinesTab } from '../DeadlinesTab'

const TODAY = new Date(2026, 9, 23) // 23 ottobre 2026

describe('DeadlinesTab', () => {
  it('groups the next twelve months by month, each row with badge, date, title, who and source', () => {
    renderWithIntl(<DeadlinesTab today={TODAY} />)

    expect(screen.getByRole('heading', { name: 'Prossimi dodici mesi' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Dicembre 2026' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Gennaio 2027' })).toBeInTheDocument()

    // 2 December 2026: marking for generative systems already on the market (public/scope-aiact.html).
    expect(screen.getByText('2 dicembre 2026')).toBeInTheDocument()
    expect(screen.getByText(/marcatura dei contenuti per i sistemi generativi/)).toBeInTheDocument()
    expect(screen.getByText(/Fornitori di sistemi generativi immessi sul mercato/)).toBeInTheDocument()
    expect(screen.getAllByText('AI Act').length).toBeGreaterThan(0)
    expect(screen.getAllByText('CELEX 32024R1689').length).toBeGreaterThan(0)

    // Quarter precision stays a quarter, and expected dates say so.
    expect(screen.getByText('primo trimestre 2027')).toBeInTheDocument()
    expect(screen.getAllByText('Data attesa, non confermata').length).toBeGreaterThan(0)

    // Beyond twelve months: not in the upcoming list.
    expect(screen.queryByText('26 luglio 2028')).not.toBeInTheDocument()
    expect(screen.queryByText('26 luglio 2029')).not.toBeInTheDocument()
  })

  it('speaks English when the interface does, with British dates and the official act names', () => {
    renderWithIntl(<DeadlinesTab today={TODAY} />, { language: 'en' })

    expect(screen.getByRole('heading', { name: 'Next twelve months' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'December 2026' })).toBeInTheDocument()
    expect(screen.getByText('2 December 2026')).toBeInTheDocument()
    expect(screen.getByText('Q1 2027')).toBeInTheDocument()
    expect(screen.getByText(/content marking for generative systems already on the market/)).toBeInTheDocument()
    expect(screen.getAllByText('Regulation (EU) 2024/1689 (AI Act)').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Verified on 23 October 2026').length).toBeGreaterThan(0)
    expect(screen.getAllByRole('link', { name: /EUR-Lex/ })[0]).toHaveAttribute(
      'href',
      expect.stringContaining('/legal-content/EN/'),
    )
  })

  it('lists the milestones already in application below, most recent first', () => {
    renderWithIntl(<DeadlinesTab today={TODAY} />)
    expect(screen.getByRole('heading', { name: 'Già in applicazione' })).toBeInTheDocument()
    expect(screen.getByText('11 settembre 2026')).toBeInTheDocument()
    expect(screen.getByText(/CRA: segnalazione di vulnerabilità/)).toBeInTheDocument()
    expect(screen.getByText('2 agosto 2026')).toBeInTheDocument()
  })

  it('dates every row and claims nothing live', () => {
    const { container } = renderWithIntl(<DeadlinesTab today={TODAY} />)
    const rows = Array.from(container.querySelectorAll('li'))
    expect(rows.length).toBeGreaterThan(0)
    for (const row of rows) {
      expect(row.textContent).toContain('Verificata il 23 ottobre 2026')
    }
    expect(container.textContent).not.toMatch(/feed attivo|in tempo reale|live/i)
  })

  it('shows an empty state when the window holds nothing', () => {
    renderWithIntl(<DeadlinesTab today={new Date(2040, 0, 1)} />)
    expect(screen.getByText('Nessuna scadenza nei prossimi dodici mesi')).toBeInTheDocument()
  })
})
