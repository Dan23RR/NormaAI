import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { SourceRow } from '../LawQuote'
import { renderWithIntl } from '@/test/i18n'
import type { Source } from '@/lib/sources'

const source: Source = {
  id: 'a-1',
  index: 1,
  act: 'Regolamento (UE) 2019/2088',
  article: 'Art. 2a',
  quote: 'Le autorità europee di vigilanza elaborano progetti di norme tecniche',
  status: 'verified',
  url: 'https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:32020R0852',
  origin: 'EUR-Lex',
}

describe('SourceRow', () => {
  it('shows where the wording was verified when it is another act', () => {
    const note = 'Testo verificato in Regolamento (UE) 2020/852 (Tassonomia), Art. 25, che lo modifica'
    renderWithIntl(<SourceRow source={{ ...source, note }} />)
    expect(screen.getByText(note)).toBeInTheDocument()
    expect(screen.getByText('Art. 2a')).toBeInTheDocument()
    expect(screen.getByRole('link')).toHaveAttribute('href', source.url)
  })

  it('shows no note otherwise', () => {
    renderWithIntl(<SourceRow source={source} />)
    expect(screen.queryByText(/Testo verificato in/)).not.toBeInTheDocument()
  })
})
