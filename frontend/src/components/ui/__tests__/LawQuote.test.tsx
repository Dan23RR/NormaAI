import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { LawQuote } from '../LawQuote'
import { renderWithIntl } from '@/test/i18n'

const passage = {
  quote: 'siano informate del fatto di stare interagendo con un sistema di IA',
  act: 'Regolamento (UE) 2024/1689',
  article: 'art. 50, par. 1',
  celex: '32024R1689',
}

describe('LawQuote', () => {
  it('claims nothing about verification when no status is passed', () => {
    renderWithIntl(<LawQuote {...passage} />)
    expect(screen.getByText(passage.quote)).toBeInTheDocument()
    expect(screen.getByText('Regolamento (UE) 2024/1689')).toBeInTheDocument()
    expect(screen.queryByText('Verificata')).not.toBeInTheDocument()
    expect(screen.queryByText('Da verificare')).not.toBeInTheDocument()
  })

  it('shows the status it is given, with the date of the check', () => {
    renderWithIntl(<LawQuote {...passage} status="verified" verifiedAt="11 novembre 2026" />)
    expect(screen.getByText('Verificata')).toBeInTheDocument()
    expect(screen.getByTitle('Verificata nel testo ufficiale il 11 novembre 2026')).toBeInTheDocument()
  })

  it('shows an unverified passage as such', () => {
    renderWithIntl(<LawQuote {...passage} status="unverified" />)
    expect(screen.getByText('Da verificare')).toBeInTheDocument()
    expect(screen.queryByText('Verificata')).not.toBeInTheDocument()
  })
})
