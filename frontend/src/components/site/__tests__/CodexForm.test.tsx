import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithIntl } from '@/test/i18n'
import { CodexForm } from '../CodexForm'

/**
 * The Codex downloads with or without consent; the address, the organisation
 * and the role leave the browser only when the consent box (unticked at the
 * start) is ticked.
 */

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn(
    async () =>
      new Response(JSON.stringify({ message: 'Scarica il Codex con il pulsante qui sotto.', download_url: '/codex-post-omnibus-2025-2029.pdf' }), {
        status: 200,
      }),
  )
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

const sent = () => JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string)

describe('Codex form', () => {
  it('starts with the consent box unticked and the address optional', () => {
    renderWithIntl(<CodexForm />)
    expect(screen.getByRole('checkbox', { name: /Potete scrivermi per email su NormaAI/ })).not.toBeChecked()
    expect(screen.getByRole('textbox', { name: 'Email di lavoro' })).not.toBeRequired()
    expect(screen.getByText('Serve solo se spunti la casella qui sotto.')).toBeInTheDocument()
  })

  it('without consent gives the Codex and sends nothing that identifies the person', async () => {
    const user = userEvent.setup()
    renderWithIntl(<CodexForm />)
    await user.type(screen.getByRole('textbox', { name: 'Email di lavoro' }), 'ada@example.test')
    await user.type(screen.getByRole('textbox', { name: 'Organizzazione' }), 'Rossi S.p.A.')
    await user.click(screen.getByRole('button', { name: 'Scarica il Codex' }))
    expect(await screen.findByRole('link', { name: 'Scarica il Codex (PDF)' })).toHaveAttribute(
      'href',
      '/codex-post-omnibus-2025-2029.pdf',
    )
    expect(sent()).toEqual({ source: 'codex_download', marketing_consent: false, contact_time: '' })
  })

  it('with consent asks for a valid address before sending anything', async () => {
    const user = userEvent.setup()
    renderWithIntl(<CodexForm />)
    await user.click(screen.getByRole('checkbox', { name: /Potete scrivermi/ }))
    expect(screen.getByRole('textbox', { name: /Email di lavoro/ })).toBeRequired()
    await user.click(screen.getByRole('button', { name: 'Scarica il Codex' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Inserisci un indirizzo email valido.')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('with consent sends the address, the organisation, the role and the choice', async () => {
    const user = userEvent.setup()
    renderWithIntl(<CodexForm />)
    await user.type(screen.getByRole('textbox', { name: 'Email di lavoro' }), 'ada@example.test')
    await user.type(screen.getByRole('textbox', { name: 'Organizzazione' }), 'Rossi S.p.A.')
    await user.click(screen.getByRole('checkbox', { name: /Potete scrivermi/ }))
    await user.click(screen.getByRole('button', { name: 'Scarica il Codex' }))
    await screen.findByRole('link', { name: 'Scarica il Codex (PDF)' })
    expect(sent()).toMatchObject({
      email: 'ada@example.test',
      org_name: 'Rossi S.p.A.',
      role: 'Compliance officer / DPO',
      source: 'codex_download',
      marketing_consent: true,
    })
  })
})
