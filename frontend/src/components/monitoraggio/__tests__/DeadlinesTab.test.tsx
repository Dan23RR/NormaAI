import { describe, it, expect } from 'vitest'
import { screen, within } from '@testing-library/react'
import { renderWithIntl, textContextFor } from '@/test/i18n'
import { dateWithArticle } from '@/lib/scope/sources'
import { verifiedOn } from '@/lib/verification'
import { DeadlinesTab } from '../DeadlinesTab'

const TODAY = new Date(2026, 10, 11) // 11 novembre 2026
const it_ = textContextFor('it')
const en = textContextFor('en')

describe('DeadlinesTab', () => {
  it('groups the next twelve months by month, each row with tag, date, title, who and what', () => {
    renderWithIntl(<DeadlinesTab today={TODAY} />)

    expect(screen.getByRole('heading', { name: 'Prossimi dodici mesi' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Dicembre 2026' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Gennaio 2027' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Luglio 2027' })).toBeInTheDocument()

    expect(screen.getAllByText('2 dicembre 2026')).toHaveLength(2)
    expect(screen.getByText(/marcatura dei contenuti per i sistemi generativi/)).toBeInTheDocument()
    expect(screen.getByText(/nuovi divieti dell’art. 5/)).toBeInTheDocument()
    expect(screen.getByText('20 gennaio 2027')).toBeInTheDocument()
    expect(screen.getByText('Regolamento macchine: applicazione')).toBeInTheDocument()
    expect(screen.getByText('31 luglio 2027')).toBeInTheDocument()
    expect(screen.getByText('7 giugno 2027')).toBeInTheDocument()
    expect(screen.getByText('30 dicembre 2026')).toBeInTheDocument()
    expect(screen.getAllByText('AI Act').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Macchine').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Parità retributiva').length).toBeGreaterThan(0)
    expect(screen.getAllByText('CELEX 32024R1689').length).toBeGreaterThan(0)

    // Beyond twelve months: not in the upcoming list.
    expect(screen.queryByText('2 dicembre 2027')).not.toBeInTheDocument()
    expect(screen.queryByText('26 luglio 2028')).not.toBeInTheDocument()
    expect(screen.queryByText('26 luglio 2029')).not.toBeInTheDocument()
  })

  it('shows for each deadline the passage of the official text that sets the date, and its own verification date', () => {
    renderWithIntl(<DeadlinesTab today={TODAY} />)

    const machinery = screen.getByText('Regolamento macchine: applicazione').closest('li') as HTMLElement
    expect(within(machinery).getByText('Esso si applica a partire dal 20 gennaio 2027')).toBeInTheDocument()
    expect(within(machinery).getByText('Regolamento (UE) 2023/1230 (regolamento macchine)')).toBeInTheDocument()
    expect(within(machinery).getByText(/art\. 54, secondo comma/)).toBeInTheDocument()
    expect(
      within(machinery).getByText(
        `Verificata ${dateWithArticle(verifiedOn('mach-54') as string, it_)} sul testo consolidato al 27 luglio 2026`,
      ),
    ).toBeInTheDocument()
    expect(within(machinery).getByRole('link', { name: /EUR-Lex/ })).toHaveAttribute(
      'href',
      expect.stringContaining('CELEX:02023R1230-20260727'),
    )

    const nis = screen.getByText(/NIS: misure di sicurezza di base/).closest('li') as HTMLElement
    expect(within(nis).getByText(/scade il 31 luglio 2027/)).toBeInTheDocument()
    expect(within(nis).getByText('ACN, determinazione n. 127434/2026')).toBeInTheDocument()
    expect(within(nis).getByText(`Verificata ${dateWithArticle(verifiedOn('acn-det-127434-2026-1-1') as string, it_)}`)).toBeInTheDocument()
    expect(within(nis).getByRole('link', { name: /ACN/ })).toHaveAttribute('href', expect.stringContaining('https://www.acn.gov.it/'))

    const pay = screen.getByText(/primi dati sul divario retributivo di genere/).closest('li') as HTMLElement
    expect(within(pay).getByRole('link', { name: /Normattiva/ })).toHaveAttribute(
      'href',
      expect.stringContaining('urn:nir:stato:decreto.legislativo:2026-05-07;96~art9'),
    )
  })

  it('speaks English when the interface does, with British dates and the official act names', () => {
    renderWithIntl(<DeadlinesTab today={TODAY} />, { language: 'en' })

    expect(screen.getByRole('heading', { name: 'Next twelve months' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'December 2026' })).toBeInTheDocument()
    expect(screen.getAllByText('2 December 2026')).toHaveLength(2)
    expect(screen.getByText(/content marking for generative systems already on the market/)).toBeInTheDocument()
    expect(screen.getAllByText('Regulation (EU) 2024/1689 (AI Act)').length).toBeGreaterThan(0)
    expect(
      screen.getAllByText(`Verified on ${dateWithArticle(verifiedOn('ai-act-111-4') as string, en)} against the text consolidated on 27 July 2026`)
        .length,
    ).toBeGreaterThan(0)
    expect(screen.getAllByRole('link', { name: /EUR-Lex/ })[0]).toHaveAttribute('href', expect.stringContaining('/legal-content/EN/'))
  })

  it('lists the milestones already in application below, most recent first', () => {
    renderWithIntl(<DeadlinesTab today={TODAY} />)
    expect(screen.getByRole('heading', { name: 'Già in applicazione' })).toBeInTheDocument()
    expect(screen.getByText('23 ottobre 2026')).toBeInTheDocument()
    expect(screen.getByText('IA nei rapporti di lavoro: D.Lgs. 179/2026 in vigore')).toBeInTheDocument()
    expect(screen.getByText('11 settembre 2026')).toBeInTheDocument()
    expect(screen.getByText('2 agosto 2026')).toBeInTheDocument()
  })

  it('gives every row a verification date and claims nothing live or internal', () => {
    const { container } = renderWithIntl(<DeadlinesTab today={TODAY} />)
    const rows = Array.from(container.querySelectorAll('li'))
    expect(rows.length).toBeGreaterThan(15)
    for (const row of rows) {
      expect(row.textContent).toMatch(/Verificata (il |l’)\d{1,2} \p{L}+ \d{4}/u)
      expect(row.textContent).not.toContain('non ancora verificata')
    }
    expect(container.textContent).not.toMatch(/feed attivo|in tempo reale|live/i)
    expect(container.textContent).not.toMatch(/\bCodex\b|\bADR-?\d|\bprompts?\b|\.planning|riga \d|\.txt|\.tsx?\b|da confermare|to be confirmed|non confermat|not confirmed/i)
    expect(container.querySelector('[title]')).toBeNull()
  })

  it('shows an empty state when the window holds nothing', () => {
    renderWithIntl(<DeadlinesTab today={new Date(2040, 0, 1)} />)
    expect(screen.getByText('Nessuna scadenza nei prossimi dodici mesi')).toBeInTheDocument()
  })
})
