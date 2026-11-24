import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ToastProvider } from '@/components/ui/Toast'
import { renderWithIntl } from '@/test/i18n'
import { ApiError } from '@/lib/api-error'
import type { User } from '@/lib/types'

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  put: vi.fn(),
  del: vi.fn(),
  upload: vi.fn(),
  fetchBlob: vi.fn(),
}))

vi.mock('@/lib/api', () => ({
  api: { get: mocks.get, put: mocks.put, del: mocks.del, upload: mocks.upload, fetchBlob: mocks.fetchBlob },
}))

import { LetterheadSection } from '../LetterheadSection'

const PATH = '/api/v1/organization/letterhead'

const admin: User = { id: 'u1', email: 'anna@studio.example', name: 'Anna', role: 'admin', organization_name: 'Studio Alfa' } as User
const member: User = { ...admin, role: 'member' }

const UNSET = {
  configured: false,
  name: 'Studio Alfa',
  address: null,
  contact: null,
  footer_note: null,
  logo: null,
  updated_at: null,
}
const SET = {
  configured: true,
  name: 'Studio Legale Alfa',
  address: 'Via Roma 1\n20121 Milano',
  contact: 'tel. 02 1234567',
  footer_note: 'Riservato al cliente.',
  logo: { content_type: 'image/png', size: 1234 },
  updated_at: '2026-11-24T10:00:00+00:00',
}

const failed = (status: number, detail?: string) => new ApiError('requestFailed', { detail, values: { status: String(status) } })

function renderSection(user: User = admin, demoMode = false) {
  return renderWithIntl(
    <ToastProvider>
      <LetterheadSection user={user} demoMode={demoMode} />
    </ToastProvider>,
  )
}

const preview = () => screen.getByRole('group', { name: 'Anteprima della carta intestata' })

describe('LetterheadSection', () => {
  const createObjectURL = vi.fn(() => 'blob:logo')
  const revokeObjectURL = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    Object.assign(URL, { createObjectURL, revokeObjectURL })
    mocks.get.mockResolvedValue(UNSET)
    mocks.fetchBlob.mockResolvedValue(new Response(new Blob(['png'], { type: 'image/png' })))
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('starts from the name of the organisation and saves what the admin writes', async () => {
    const user = userEvent.setup()
    mocks.put.mockResolvedValue({ ...SET, logo: null })
    renderSection()

    expect(await screen.findByText('Per ora i PDF portano solo il nome dell’organizzazione. Completa i dati e salva.')).toBeInTheDocument()
    expect(within(preview()).getByText('Studio Alfa')).toBeInTheDocument()
    expect(within(preview()).getByText('Pagina 1 di 3 · Controllo eseguito con NormaAI')).toBeInTheDocument()
    const name = screen.getByLabelText(/Nome dello studio/)
    expect(name).toHaveValue('Studio Alfa')

    await user.clear(name)
    await user.type(name, 'Studio Legale Alfa')
    await user.type(screen.getByLabelText('Indirizzo'), 'Via Roma 1{Enter}20121 Milano')
    await user.type(screen.getByLabelText('Contatti'), 'tel. 02 1234567')
    await user.type(screen.getByLabelText('Nota a piè di pagina'), 'Riservato al cliente.')
    // The preview follows what is typed.
    expect(within(preview()).getByText('Studio Legale Alfa')).toBeInTheDocument()
    expect(within(preview()).getByText('20121 Milano')).toBeInTheDocument()
    expect(within(preview()).getByText('Riservato al cliente.')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Salva la carta intestata' }))
    await waitFor(() =>
      expect(mocks.put).toHaveBeenCalledWith(PATH, {
        name: 'Studio Legale Alfa',
        address: 'Via Roma 1\n20121 Milano',
        contact: 'tel. 02 1234567',
        footer_note: 'Riservato al cliente.',
      }),
    )
    expect(await screen.findByText('Carta intestata salvata')).toBeInTheDocument()
    expect(screen.queryByText(/Per ora i PDF portano solo/)).not.toBeInTheDocument()
  })

  it('says what to change before sending, and shows what the server refuses', async () => {
    const user = userEvent.setup()
    renderSection()
    const name = await screen.findByLabelText(/Nome dello studio/)
    await user.clear(name)
    await user.type(screen.getByLabelText('Indirizzo'), 'uno{Enter}due{Enter}tre{Enter}quattro')
    await user.click(screen.getByRole('button', { name: 'Salva la carta intestata' }))
    expect(screen.getByText('Scrivi il nome dello studio.')).toBeInTheDocument()
    expect(screen.getByText('L’indirizzo può avere al massimo 3 righe.')).toBeInTheDocument()
    expect(name).toHaveAttribute('aria-invalid', 'true')
    expect(mocks.put).not.toHaveBeenCalled()

    mocks.put.mockRejectedValueOnce(failed(422, 'Il nome dello studio può avere al massimo 200 caratteri.'))
    await user.type(name, 'Studio')
    await user.clear(screen.getByLabelText('Indirizzo'))
    await user.click(screen.getByRole('button', { name: 'Salva la carta intestata' }))
    expect(await screen.findByText('Il nome dello studio può avere al massimo 200 caratteri.')).toBeInTheDocument()
  })

  it('shows the stored letterhead with its logo, and lets the admin replace or remove the logo', async () => {
    // A file the picker would hide still reaches the page when dropped or chosen with "all files".
    const user = userEvent.setup({ applyAccept: false })
    mocks.get.mockResolvedValue(SET)
    mocks.upload.mockResolvedValue(SET)
    mocks.del.mockResolvedValue({ ...SET, logo: null })
    renderSection()

    const logo = await screen.findByRole('img', { name: 'Logo dello studio' })
    expect(preview()).toContainElement(logo)
    expect(logo).toHaveAttribute('src', 'blob:logo')
    expect(mocks.fetchBlob).toHaveBeenCalledWith(`${PATH}/logo`)
    expect(within(preview()).getByText('Riservato al cliente.')).toBeInTheDocument()

    // A file that is not a PNG or a JPEG is refused here, without calling the server.
    const input = screen.getByLabelText('Sostituisci il logo')
    await user.upload(input, new File(['gif'], 'logo.gif', { type: 'image/gif' }))
    expect(await screen.findByText('Il logo deve essere un’immagine PNG o JPEG.')).toBeInTheDocument()
    expect(mocks.upload).not.toHaveBeenCalled()

    const png = new File(['png'], 'logo.png', { type: 'image/png' })
    await user.upload(input, png)
    await waitFor(() => expect(mocks.upload).toHaveBeenCalledTimes(1))
    const [path, form, method] = mocks.upload.mock.calls[0] as [string, FormData, string]
    expect(path).toBe(`${PATH}/logo`)
    expect(method).toBe('PUT')
    expect((form.get('file') as File).name).toBe('logo.png')
    expect(await screen.findByText('Logo salvato')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Rimuovi il logo' }))
    await waitFor(() => expect(mocks.del).toHaveBeenCalledWith(`${PATH}/logo`))
    expect(await screen.findByText('Logo rimosso')).toBeInTheDocument()
    expect(within(preview()).queryByRole('img')).not.toBeInTheDocument()
    expect(screen.getByText('Nessun logo.')).toBeInTheDocument()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:logo')
  })

  it('refuses a logo heavier than 2 MB before sending it', async () => {
    const user = userEvent.setup()
    renderSection()
    const input = await screen.findByLabelText('Carica un logo')
    const heavy = new File([new Uint8Array(2 * 1024 * 1024 + 1)], 'logo.png', { type: 'image/png' })
    await user.upload(input, heavy)
    expect(await screen.findByText('Il logo supera 2 MB: usa un file più leggero.')).toBeInTheDocument()
    expect(mocks.upload).not.toHaveBeenCalled()
  })

  it('deletes the letterhead only after a confirmation', async () => {
    const user = userEvent.setup()
    mocks.get.mockResolvedValueOnce(SET).mockResolvedValue(UNSET)
    mocks.del.mockResolvedValue(undefined)
    renderSection()
    await user.click(await screen.findByRole('button', { name: 'Elimina la carta intestata' }))
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText('Testi e logo vengono cancellati. I PDF porteranno solo il nome dell’organizzazione.')).toBeInTheDocument()
    expect(mocks.del).not.toHaveBeenCalled()
    await user.click(within(dialog).getByRole('button', { name: 'Elimina' }))
    await waitFor(() => expect(mocks.del).toHaveBeenCalledWith(PATH))
    expect(await screen.findByText('Carta intestata eliminata')).toBeInTheDocument()
    expect(await screen.findByText(/Per ora i PDF portano solo il nome/)).toBeInTheDocument()
  })

  it('shows the letterhead to the members, who cannot change it', async () => {
    mocks.get.mockResolvedValue(SET)
    renderSection(member)
    expect(await screen.findByText('Solo un amministratore dell’organizzazione può modificarla.')).toBeInTheDocument()
    expect(within(preview()).getByText('Studio Legale Alfa')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Salva la carta intestata' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Sostituisci il logo')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Elimina la carta intestata' })).not.toBeInTheDocument()
  })

  it('says in the demo that there is no letterhead to set, and calls nothing', () => {
    renderSection(admin, true)
    expect(screen.getByText(/Nella demo con dati di esempio la carta intestata non si imposta/)).toBeInTheDocument()
    expect(mocks.get).not.toHaveBeenCalled()
  })

  it('says when the letterhead did not load and tries again', async () => {
    const user = userEvent.setup()
    mocks.get.mockRejectedValueOnce(failed(503)).mockResolvedValue(UNSET)
    renderSection()
    expect(await screen.findByRole('alert')).toHaveTextContent('La carta intestata non si è caricata. Riprova.')
    await user.click(screen.getByRole('button', { name: 'Riprova il caricamento' }))
    expect(await screen.findByLabelText(/Nome dello studio/)).toHaveValue('Studio Alfa')
  })
})
