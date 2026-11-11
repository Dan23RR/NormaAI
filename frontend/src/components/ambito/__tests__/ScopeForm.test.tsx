import { describe, it, expect, vi } from 'vitest'
import { fireEvent, screen } from '@testing-library/react'
import { renderWithIntl } from '@/test/i18n'
import { EMPTY_INPUT, NO_MACHINERY, NO_NIS, keysToWork } from '@/lib/scope/query'
import type { ScopeInput } from '@/lib/scope/types'
import { NIS_SECTORS } from '@/lib/scope/types'
import { ScopeForm } from '../ScopeForm'

function renderForm(value: ScopeInput = EMPTY_INPUT, language: 'it' | 'en' = 'it') {
  const onChange = vi.fn()
  const onSubmit = vi.fn()
  renderWithIntl(
    <ScopeForm
      value={value}
      onChange={onChange}
      onSubmit={onSubmit}
      onReset={() => {}}
      clients={[]}
      clientsLoading={false}
      onLoadClient={() => {}}
    />,
    { language },
  )
  return { onChange, onSubmit }
}

describe('ScopeForm', () => {
  it('asks the company figures and one group of questions per rule set', () => {
    renderForm()
    expect(screen.getByLabelText('Dipendenti')).toBeInTheDocument()
    expect(screen.getByLabelText('Ricavi netti annui')).toBeInTheDocument()
    expect(screen.getByLabelText('Totale di bilancio')).toBeInTheDocument()
    for (const legend of [
      'IA nei rapporti di lavoro (D.Lgs. 179/2026, legge 132/2025, AI Act)',
      'Cybersicurezza: decreto NIS (D.Lgs. 138/2024)',
      'Macchine: regolamento (UE) 2023/1230',
      'Intelligenza artificiale: trasparenza (AI Act, art. 50)',
      'CSRD e CSDDD: casi particolari',
    ]) {
      expect(screen.getByRole('group', { name: legend })).toBeInTheDocument()
    }
  })

  it('lists every sector of the annexes of the NIS decree, in both languages', () => {
    renderForm()
    const select = screen.getByLabelText("Settore dell'allegato") as HTMLSelectElement
    const values = Array.from(select.options).map((o) => o.value)
    expect(values).toEqual(['', ...NIS_SECTORS])
    expect(screen.getByRole('option', { name: 'Infrastrutture digitali' })).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Allegato II: altri settori critici' })).toBeInTheDocument()
  })

  it('keeps a group unanswered until the person answers it', () => {
    const { onChange } = renderForm()
    expect((screen.getByLabelText(/Nessuna di queste situazioni riguarda l'impresa/) as HTMLInputElement).checked).toBe(false)

    fireEvent.click(screen.getByLabelText(/Un sistema di IA contribuisce a decisioni sul personale/))
    expect(onChange).toHaveBeenLastCalledWith({ ...EMPTY_INPUT, work: keysToWork(['dec']) })

    fireEvent.click(screen.getByLabelText(/Nessuno di questi ruoli riguarda l'impresa/))
    expect(onChange).toHaveBeenLastCalledWith({ ...EMPTY_INPUT, machinery: NO_MACHINERY })

    fireEvent.change(screen.getByLabelText("Settore dell'allegato"), { target: { value: 'fabbricazione' } })
    expect(onChange).toHaveBeenLastCalledWith({ ...EMPTY_INPUT, nis: { ...NO_NIS, sector: 'fabbricazione' } })

    fireEvent.click(screen.getByLabelText(/È un'impresa collegata a un soggetto NIS/))
    expect(onChange).toHaveBeenLastCalledWith({ ...EMPTY_INPUT, nis: { ...NO_NIS, linked: true } })
  })

  it('withdraws an answer when "none" is unticked or the sector goes back to unanswered', () => {
    const { onChange } = renderForm({ ...EMPTY_INPUT, machinery: NO_MACHINERY, nis: { ...NO_NIS, sector: 'energia' } })
    fireEvent.click(screen.getByLabelText(/Nessuno di questi ruoli riguarda l'impresa/))
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ machinery: null }))
    fireEvent.change(screen.getByLabelText("Settore dell'allegato"), { target: { value: '' } })
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ nis: null }))
  })

  it('speaks English', () => {
    renderForm(EMPTY_INPUT, 'en')
    expect(screen.getByRole('group', { name: 'Machinery: Regulation (EU) 2023/1230' })).toBeInTheDocument()
    expect(screen.getByLabelText('Balance sheet total')).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Digital infrastructure' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Check the scope' })).toBeInTheDocument()
  })
})
