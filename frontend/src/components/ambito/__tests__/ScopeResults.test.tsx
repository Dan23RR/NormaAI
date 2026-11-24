import { describe, it, expect } from 'vitest'
import { screen, within } from '@testing-library/react'
import { renderWithIntl, textContextFor } from '@/test/i18n'
import { assessScope } from '@/lib/scope/rules'
import { EMPTY_INPUT, NO_NIS, keysToMachinery, keysToWork } from '@/lib/scope/query'
import { dateWithArticle } from '@/lib/scope/sources'
import type { ScopeAssessment } from '@/lib/scope/types'
import { verifiedOn } from '@/lib/verification'
import { ScopeResults } from '../ScopeResults'
import { SourceEntry } from '../SourceCitation'

const it_ = textContextFor('it')
const noop = () => {}

function assessment(language: 'it' | 'en' = 'it'): ScopeAssessment {
  return assessScope(
    {
      ...EMPTY_INPUT,
      name: 'Officine Esempio Srl',
      employees: 60,
      turnoverEur: 12_000_000,
      nis: { ...NO_NIS, sector: 'fabbricazione' },
      work: keysToWork(['dec']),
      machinery: keysToMachinery(['imp']),
    },
    textContextFor(language),
  )
}

describe('ScopeResults', () => {
  it('shows the six rule sets, what applies first, each as a first indicative filter', () => {
    renderWithIntl(<ScopeResults assessment={assessment()} onCopyResult={noop} onCopyLink={noop} />)
    const titles = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)
    expect(titles).toEqual([
      'Risultato',
      'IA nei rapporti di lavoro',
      'NIS, cybersicurezza (D.Lgs. 138/2024)',
      'Regolamento macchine (UE) 2023/1230',
      'CSRD, rendicontazione di sostenibilità',
      'CSDDD, dovere di diligenza',
      'AI Act, trasparenza (art. 50)',
    ])
    expect(screen.getAllByText('Si applica')).toHaveLength(3)
    expect(screen.getAllByText('Non si applica')).toHaveLength(2)
    expect(screen.getAllByText('Non valutato')).toHaveLength(1)
    expect(screen.getAllByText(/Primo filtro indicativo, non un parere legale/)).toHaveLength(6)
  })

  it('gives each duty its article and each source its own verification date and official passage', () => {
    renderWithIntl(<ScopeResults assessment={assessment()} onCopyResult={noop} onCopyLink={noop} />)
    const machinery = screen.getByRole('region', { name: 'Regolamento macchine (UE) 2023/1230' })
    expect(within(machinery).getByText('Si applica dal 20 gennaio 2027 (art. 54)')).toBeInTheDocument()
    expect(within(machinery).getByText('Importare solo prodotti conformi e verificare il lavoro del fabbricante')).toBeInTheDocument()
    expect(within(machinery).getByText('art. 13, par. 1')).toBeInTheDocument()
    expect(within(machinery).getByText('Esso si applica a partire dal 20 gennaio 2027')).toBeInTheDocument()
    expect(
      within(machinery).getAllByText(`Verificata ${dateWithArticle(verifiedOn('mach-54') as string, it_)} sul testo consolidato al 27 luglio 2026`)
        .length,
    ).toBeGreaterThan(0)
    expect(within(machinery).getByText(/fonti, \d+ verificate sul testo ufficiale/)).toBeInTheDocument()

    const work = screen.getByRole('region', { name: 'IA nei rapporti di lavoro' })
    expect(within(work).getByText('Decisioni sul rapporto di lavoro: mai solo automatiche')).toBeInTheDocument()
    expect(within(work).getAllByRole('link', { name: /Normattiva/ }).length).toBeGreaterThan(0)
    expect(within(work).getAllByText(`Verificata ${dateWithArticle(verifiedOn('dlgs-179-2026-41-1') as string, it_)}`).length).toBeGreaterThan(0)
  })

  it('never says verified without a check: an unverified source is shown as indicated only, with no passage', () => {
    const source = assessment().results[0].sources[0]
    renderWithIntl(
      <ul>
        <SourceEntry source={{ ...source, status: 'unverified', verifiedAt: undefined, quote: 'testo non confermato dal controllo' }} />
      </ul>,
    )
    expect(screen.getByText('Fonte indicata, non ancora verificata')).toBeInTheDocument()
    expect(screen.queryByText(/Verificata/)).not.toBeInTheDocument()
    expect(screen.queryByText('testo non confermato dal controllo')).not.toBeInTheDocument()
  })

  it('speaks English with the English article labels', () => {
    renderWithIntl(<ScopeResults assessment={assessment('en')} onCopyResult={noop} onCopyLink={noop} />, { language: 'en' })
    const machinery = screen.getByRole('region', { name: 'Machinery Regulation (EU) 2023/1230' })
    expect(within(machinery).getByText('Applies from 20 January 2027 (Art. 54)')).toBeInTheDocument()
    expect(within(machinery).getByText('Art. 13(1)')).toBeInTheDocument()
    expect(screen.getAllByText(/A first indicative filter, not legal advice/)).toHaveLength(6)
  })
})
