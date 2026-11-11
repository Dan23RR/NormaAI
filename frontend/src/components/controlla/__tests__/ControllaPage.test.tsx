import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ToastProvider } from '@/components/ui/Toast'
import { renderWithIntl } from '@/test/i18n'
import { ApiError } from '@/lib/api-error'
import { DEMO_CLIENTS } from '@/lib/mock-data'
import { DEMO_DOCUMENTS, demoDocumentsRoute, resetDemoDocuments } from '@/lib/mock-documents'

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  upload: vi.fn(),
  patch: vi.fn(),
  push: vi.fn(),
  state: { demo: false, search: '' },
}))

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mocks.push, replace: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(mocks.state.search),
  usePathname: () => '/app/controlla',
  useParams: () => ({}),
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
  useAuth: () => ({ demoMode: mocks.state.demo, user: { name: 'Demo User', role: 'admin' } }),
}))

vi.mock('@/lib/api', () => ({
  api: { get: mocks.get, post: mocks.post, upload: mocks.upload, patch: mocks.patch },
}))

import { ControllaPage } from '../ControllaPage'
import { recallCheck, forgetCheck } from '../documents-api'

/** The server of the tests: the clients and the canned checks, by path. */
function serve(path: string): unknown {
  if (path.startsWith('/api/v1/clients')) return DEMO_CLIENTS
  const answer = demoDocumentsRoute('GET', path)
  if (answer.handled) return answer.value
  throw new Error(`unexpected GET ${path}`)
}

const failed = (status: number, detail?: string) => new ApiError('requestFailed', { detail, values: { status: String(status) } })

function renderPage(language: 'it' | 'en' = 'it') {
  return renderWithIntl(
    <ToastProvider>
      <ControllaPage />
    </ToastProvider>,
    { language },
  )
}

const docx = (name = 'nota.docx', content = 'art. 13 del GDPR') => new File([content], name, { type: 'application/octet-stream' })

describe('ControllaPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    resetDemoDocuments()
    forgetCheck()
    mocks.state.demo = false
    mocks.state.search = ''
    mocks.get.mockImplementation(async (path: string) => serve(path))
    mocks.patch.mockImplementation(async (_path: string, body: unknown) => body)
  })

  it('shows the form, what is kept of a document, and the checked documents with their state', async () => {
    renderPage()
    expect(screen.getByRole('heading', { level: 1, name: 'Controlla' })).toBeInTheDocument()
    expect(screen.getByText('Controlla i riferimenti di legge dei tuoi documenti sul testo vigente.')).toBeInTheDocument()

    // The form: surveillance is on unless the person turns it off.
    const form = screen.getByRole('form', { name: 'Nuovo controllo' })
    expect(within(form).getByLabelText('Scegli un file')).toHaveAttribute('accept', '.docx,.pdf,.html,.txt,.md,.htm')
    expect(within(form).getByText('File .docx, .pdf con testo selezionabile, .html, .txt o .md, fino a 10 MB.')).toBeInTheDocument()
    expect(within(form).getByRole('checkbox', { name: /Sorveglia questo documento/ })).toBeChecked()
    expect(within(form).getByRole('button', { name: 'Controlla il documento' })).toBeInTheDocument()

    // Next to the upload: the file is not stored, and this is what is.
    const note = screen.getByRole('complementary', { name: 'Il documento non viene conservato' })
    expect(within(note).getByText(/viene letto in memoria per il tempo del controllo, poi scartato/)).toBeInTheDocument()
    expect(within(note).getByText('il nome del file e la sua impronta SHA-256;')).toBeInTheDocument()
    expect(within(note).getByText(/al massimo 160 caratteri di contesto, le citazioni e l'esito;/)).toBeInTheDocument()
    expect(within(note).getByText('le norme da cui il documento dipende, per poterle ricontrollare.')).toBeInTheDocument()
    expect(within(form).getByText(/Il documento non viene conservato: restano il nome, l'impronta, le date/)).toBeInTheDocument()

    // The list: status, date, client, surveillance.
    const table = await screen.findByRole('table')
    const rows = within(table).getAllByRole('row')
    expect(rows).toHaveLength(1 + DEMO_DOCUMENTS.length)

    const gdpr = within(table).getByRole('link', { name: 'Procedura violazioni dati personali.docx' }).closest('tr') as HTMLElement
    expect(within(gdpr).getByRole('link', { name: 'Procedura violazioni dati personali.docx' })).toHaveAttribute(
      'href',
      '/app/controlla/demo-doc-gdpr',
    )
    expect(within(gdpr).getByText('Da correggere')).toBeInTheDocument()
    expect(within(gdpr).getByText('2 da correggere, 1 da controllare, 4 a posto, 1 non coperto')).toBeInTheDocument()
    expect(within(gdpr).getByRole('link', { name: 'Beta Software S.r.l.' })).toHaveAttribute('href', '/app/clienti/demo-c2')
    expect(within(gdpr).getAllByText('2026-11-10').length).toBeGreaterThan(0)
    expect(within(gdpr).getByText('Attiva')).toBeInTheDocument()

    // A check to review says so before anything else.
    const csddd = within(table).getByRole('link', { name: 'Nota fornitori dovere di diligenza.docx' }).closest('tr') as HTMLElement
    expect(within(csddd).getByText('Da rivedere')).toBeInTheDocument()
    expect(within(csddd).getByText('una norma citata è cambiata')).toBeInTheDocument()
    expect(within(csddd).queryByText('A posto')).not.toBeInTheDocument()

    const clause = within(table).getByRole('link', { name: 'Processor clause (draft).txt' }).closest('tr') as HTMLElement
    expect(within(clause).getByText('Nessuno')).toBeInTheDocument()
    expect(within(clause).getByText('Non attiva')).toBeInTheDocument()

    expect(screen.getByText('4 di 4 documenti')).toBeInTheDocument()
    // The tabs carry the counts.
    await waitFor(() => expect(screen.getByRole('tab', { name: /Da rivedere/ })).toHaveTextContent('1'))
    expect(screen.getByRole('tab', { name: /Tutti/ })).toHaveTextContent('4')
  })

  it('filters the documents to review, on the server', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByRole('link', { name: 'Policy uso IA.pdf' })

    await user.click(screen.getByRole('tab', { name: /Da rivedere/ }))
    await waitFor(() =>
      expect(mocks.get).toHaveBeenCalledWith('/api/v1/documents/checks?needs_review=true&limit=20&offset=0'),
    )
    expect(await screen.findByText('1 di 1 documenti')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Nota fornitori dovere di diligenza.docx' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Policy uso IA.pdf' })).not.toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Da rivedere/ })).toHaveAttribute('aria-selected', 'true')

    await user.click(screen.getByRole('tab', { name: /Tutti/ }))
    expect(await screen.findByRole('link', { name: 'Policy uso IA.pdf' })).toBeInTheDocument()
    expect(mocks.get).toHaveBeenLastCalledWith('/api/v1/documents/checks?limit=20&offset=0')
  })

  it('says so when nothing is to review, and leads back to all the documents', async () => {
    const user = userEvent.setup()
    mocks.get.mockImplementation(async (path: string) => {
      if (path.includes('needs_review=true')) return { items: [], total: 0 }
      return serve(path)
    })
    renderPage()
    await screen.findByRole('link', { name: 'Policy uso IA.pdf' })
    await user.click(screen.getByRole('tab', { name: /Da rivedere/ }))
    expect(await screen.findByText('Nessun documento da rivedere')).toBeInTheDocument()
    expect(screen.getByText('Finora nessun ricontrollo ha segnalato cambiamenti nelle norme citate dai tuoi documenti.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Mostra tutti i documenti' }))
    expect(await screen.findByRole('link', { name: 'Policy uso IA.pdf' })).toBeInTheDocument()
  })

  it('invites to the first check when there is none, and says when the list did not load', async () => {
    mocks.get.mockImplementation(async (path: string) => {
      if (path.startsWith('/api/v1/documents/checks')) return { items: [], total: 0 }
      return serve(path)
    })
    const first = renderPage()
    expect(await screen.findByText('Nessun documento controllato')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    first.unmount()

    const user = userEvent.setup()
    let fail = true
    mocks.get.mockImplementation(async (path: string) => {
      if (fail && path.startsWith('/api/v1/documents/checks')) throw new ApiError('network')
      return serve(path)
    })
    renderPage()
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('I documenti controllati non si sono caricati')
    expect(alert).toHaveTextContent('Il server non risponde. Riprova tra un minuto; se il problema continua, scrivi a info@normaai.org.')
    fail = false
    await user.click(within(alert).getByRole('button', { name: 'Riprova il caricamento' }))
    expect(await screen.findByRole('table')).toBeInTheDocument()
  })

  it('loads the next page on request', async () => {
    const user = userEvent.setup()
    const summaries = DEMO_DOCUMENTS.map(({ findings: _f, dependencies: _d, ...summary }) => summary)
    mocks.get.mockImplementation(async (path: string) => {
      if (path.startsWith('/api/v1/documents/checks') && !path.includes('needs_review')) {
        const offset = Number(new URL(path, 'http://x').searchParams.get('offset'))
        return { items: summaries.slice(offset, offset + 2), total: summaries.length }
      }
      return serve(path)
    })
    renderPage()
    expect(await screen.findByText('2 di 4 documenti')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Mostra altri documenti' }))
    expect(await screen.findByText('4 di 4 documenti')).toBeInTheDocument()
    expect(mocks.get).toHaveBeenCalledWith('/api/v1/documents/checks?limit=20&offset=2')
    expect(screen.queryByRole('button', { name: 'Mostra altri documenti' })).not.toBeInTheDocument()
  })

  it('refuses a format, an empty file and a file over 10 MB before calling the server', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByRole('table')
    const form = screen.getByRole('form', { name: 'Nuovo controllo' })
    const zone = within(form).getByRole('group', { name: 'Documento da controllare' })

    await user.click(within(form).getByRole('button', { name: 'Controlla il documento' }))
    expect(within(form).getByRole('alert')).toHaveTextContent('Scegli un file o trascinalo nel riquadro, oppure passa a «Incolla il testo».')

    // A dropped file does not go through the picker's filter.
    fireEvent.drop(zone, { dataTransfer: { files: [new File(['x'], 'scansione.png')] } })
    expect(within(form).getByRole('alert')).toHaveTextContent(
      'Formato non supportato (.png). Carica un file .docx, .pdf, .html, .txt o .md, oppure incolla il testo.',
    )
    expect(within(form).getByText(/File scelto: scansione\.png/)).toBeInTheDocument()

    fireEvent.drop(zone, { dataTransfer: { files: [new File([], 'vuoto.docx')] } })
    expect(within(form).getByRole('alert')).toHaveTextContent('Il file è vuoto.')

    const big = docx('grande.pdf')
    Object.defineProperty(big, 'size', { value: 10 * 1024 * 1024 + 1 })
    fireEvent.drop(zone, { dataTransfer: { files: [big] } })
    // One byte over the limit is shown rounded up, never as the limit itself.
    expect(within(form).getByRole('alert')).toHaveTextContent(/Il file pesa 10[.,]1 MB: il limite è 10 MB\. Riducilo oppure incolla il testo\./)

    await user.click(within(form).getByRole('button', { name: 'Controlla il documento' }))
    expect(mocks.upload).not.toHaveBeenCalled()

    await user.click(within(form).getByRole('button', { name: 'Togli il file' }))
    expect(within(form).queryByText(/File scelto/)).not.toBeInTheDocument()
    expect(within(form).queryByRole('alert')).not.toBeInTheDocument()
  })

  it('checks a file with the client, the date and surveillance as chosen, then opens the check', async () => {
    const user = userEvent.setup()
    const result = DEMO_DOCUMENTS[1]
    mocks.upload.mockResolvedValue(result)
    renderPage()
    await screen.findByRole('table')
    const form = screen.getByRole('form', { name: 'Nuovo controllo' })

    const file = docx('Policy uso IA.docx')
    await user.upload(within(form).getByLabelText('Scegli un file'), file)
    expect(within(form).getByText(/File scelto: Policy uso IA\.docx \(16 B\)/)).toBeInTheDocument()
    await user.selectOptions(within(form).getByLabelText('Cliente'), 'Epsilon Salute S.r.l.')
    fireEvent.change(within(form).getByLabelText('Data del documento'), { target: { value: '2026-03-15' } })
    await user.click(within(form).getByRole('checkbox', { name: /Sorveglia questo documento/ }))
    await user.click(within(form).getByRole('button', { name: 'Controlla il documento' }))

    await waitFor(() => expect(mocks.upload).toHaveBeenCalledTimes(1))
    const [path, body] = mocks.upload.mock.calls[0] as [string, FormData]
    expect(path).toBe('/api/v1/documents/check')
    expect(body.get('file')).toBe(file)
    expect(body.get('client_id')).toBe('demo-c5')
    expect(body.get('document_date')).toBe('2026-03-15')
    expect(body.get('watch')).toBe('false')

    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith('/app/controlla/demo-doc-ai'))
    // The page of the check gets what the server already answered, as a real result.
    expect(recallCheck('demo-doc-ai')).toEqual({ check: result, example: false })
  })

  it('sends only what was chosen: no client, no date, surveillance on', async () => {
    const user = userEvent.setup()
    mocks.upload.mockResolvedValue(DEMO_DOCUMENTS[0])
    renderPage()
    await screen.findByRole('table')
    const form = screen.getByRole('form', { name: 'Nuovo controllo' })
    await user.upload(within(form).getByLabelText('Scegli un file'), docx())
    await user.click(within(form).getByRole('button', { name: 'Controlla il documento' }))
    await waitFor(() => expect(mocks.upload).toHaveBeenCalledTimes(1))
    const body = mocks.upload.mock.calls[0][1] as FormData
    expect(body.has('client_id')).toBe(false)
    expect(body.has('document_date')).toBe(false)
    expect(body.get('watch')).toBe('true')
  })

  it('checks a pasted text, with a name of its own or the default one', async () => {
    const user = userEvent.setup()
    mocks.post.mockResolvedValue(DEMO_DOCUMENTS[0])
    renderPage()
    await screen.findByRole('table')
    const form = screen.getByRole('form', { name: 'Nuovo controllo' })
    await user.click(within(form).getByRole('tab', { name: 'Incolla il testo' }))

    await user.click(within(form).getByRole('button', { name: 'Controlla il documento' }))
    expect(within(form).getByRole('alert')).toHaveTextContent('Incolla il testo da controllare.')
    expect(mocks.post).not.toHaveBeenCalled()

    await user.type(within(form).getByLabelText(/Testo del documento/), "Ai sensi dell'art. 13 del GDPR")
    await user.click(within(form).getByRole('button', { name: 'Controlla il documento' }))
    await waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(1))
    expect(mocks.post).toHaveBeenCalledWith('/api/v1/documents/check', {
      text: "Ai sensi dell'art. 13 del GDPR",
      filename: 'Testo incollato',
      watch: true,
    })
    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith('/app/controlla/demo-doc-gdpr'))
  })

  it('refuses a date in the future', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByRole('table')
    const form = screen.getByRole('form', { name: 'Nuovo controllo' })
    await user.upload(within(form).getByLabelText('Scegli un file'), docx())
    fireEvent.change(within(form).getByLabelText('Data del documento'), { target: { value: '2999-01-01' } })
    await user.click(within(form).getByRole('button', { name: 'Controlla il documento' }))
    expect(within(form).getByRole('alert')).toHaveTextContent('La data del documento non può essere nel futuro.')
    expect(mocks.upload).not.toHaveBeenCalled()
  })

  it.each([
    [413, 'Il documento è troppo grande: un file può pesare al massimo 10 MB. Riducilo, dividilo in parti oppure incolla solo il testo che ti serve.'],
    [415, 'Il server non legge questo formato. Carica un file .docx, .pdf con testo selezionabile, .html, .txt o .md, oppure incolla il testo.'],
    [
      422,
      "Il server non ha potuto controllare il documento così com'è. Se è un PDF fatto di sole immagini, protetto da password o danneggiato, incolla il testo oppure carica una versione con testo selezionabile.",
    ],
    [429, "Troppe richieste in poco tempo, oppure c'è già un controllo in corso. Aspetta un momento e riprova."],
    [
      504,
      'Il controllo ha superato il tempo massimo prima di finire. Riprova tra qualche minuto; se il documento è molto lungo, controllane una parte alla volta.',
    ],
    [500, 'Il server ha avuto un problema. Riprova tra qualche minuto; se continua, scrivi a info@normaai.org.'],
  ])('says what happened and what to do when the server answers %i', async (status, message) => {
    const user = userEvent.setup()
    mocks.upload.mockRejectedValue(failed(status, status === 429 ? 'Troppe richieste. Riprova tra 2 minuti.' : undefined))
    renderPage()
    await screen.findByRole('table')
    const form = screen.getByRole('form', { name: 'Nuovo controllo' })
    await user.upload(within(form).getByLabelText('Scegli un file'), docx())
    await user.click(within(form).getByRole('button', { name: 'Controlla il documento' }))

    const alert = await within(form).findByRole('alert')
    expect(alert).toHaveTextContent('Il controllo non è riuscito')
    expect(alert).toHaveTextContent(message)
    expect(alert).toHaveTextContent(`Codice ${status}`)
    if (status === 429) expect(alert).toHaveTextContent('Dal server: Troppe richieste. Riprova tra 2 minuti.')
    expect(mocks.push).not.toHaveBeenCalled()
    // The form is usable again: same file, another try.
    expect(within(form).getByRole('button', { name: 'Controlla il documento' })).toBeEnabled()
  })

  it('says when the server does not answer at all', async () => {
    const user = userEvent.setup()
    mocks.upload.mockRejectedValue(new ApiError('network'))
    renderPage()
    await screen.findByRole('table')
    const form = screen.getByRole('form', { name: 'Nuovo controllo' })
    await user.upload(within(form).getByLabelText('Scegli un file'), docx())
    await user.click(within(form).getByRole('button', { name: 'Controlla il documento' }))
    const alert = await within(form).findByRole('alert')
    expect(alert).toHaveTextContent('Il server non risponde. Riprova tra un minuto; se il problema continua, scrivi a info@normaai.org.')
    expect(alert).not.toHaveTextContent('Codice')
  })

  it('preselects the client of the link that led here', async () => {
    mocks.state.search = 'cliente=demo-c3'
    renderPage()
    await screen.findByRole('table')
    await waitFor(() => expect(screen.getByLabelText('Cliente')).toHaveValue('demo-c3'))
  })

  it('works without the list of clients, and says it', async () => {
    mocks.get.mockImplementation(async (path: string) => {
      if (path.startsWith('/api/v1/clients')) throw new ApiError('network')
      return serve(path)
    })
    renderPage()
    const table = await screen.findByRole('table')
    expect(
      await screen.findByText("L'elenco dei clienti non si è caricato: puoi fare il controllo senza collegarlo a un cliente."),
    ).toBeInTheDocument()
    // The names are not known: the list does not invent them.
    const gdpr = within(table).getByRole('link', { name: 'Procedura violazioni dati personali.docx' }).closest('tr') as HTMLElement
    expect(within(gdpr).getByText('n.d.')).toBeInTheDocument()
  })

  it('declares the demo before the upload and hands over the example as an example', async () => {
    const user = userEvent.setup()
    mocks.state.demo = true
    mocks.upload.mockResolvedValue(DEMO_DOCUMENTS[0])
    renderPage()
    await screen.findByRole('table')
    const form = screen.getByRole('form', { name: 'Nuovo controllo' })
    expect(
      within(form).getByText(
        'Demo con dati di esempio: il documento che scegli non viene letto né inviato. Il controllo apre il risultato di un documento di esempio.',
      ),
    ).toBeInTheDocument()
    await user.upload(within(form).getByLabelText('Scegli un file'), docx('il mio contratto.docx'))
    await user.click(within(form).getByRole('button', { name: 'Controlla il documento' }))
    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith('/app/controlla/demo-doc-gdpr'))
    expect(recallCheck('demo-doc-gdpr')?.example).toBe(true)
    expect(screen.getByText('Demo con dati di esempio: non parte nessuna email.')).toBeInTheDocument()
  })

  it('saves the choice about the email digest', async () => {
    const user = userEvent.setup()
    renderPage()
    const box = await screen.findByRole('checkbox', { name: /Riepilogo via email dei documenti da rivedere/ })
    expect(box).toBeChecked()
    await user.click(box)
    await waitFor(() => expect(mocks.patch).toHaveBeenCalledWith('/api/v1/documents/preferences', { email_digest: false }))
    expect(await screen.findByText('Non riceverai il riepilogo via email.')).toBeInTheDocument()
    expect(box).not.toBeChecked()
  })

  it('puts the box back when the choice could not be saved', async () => {
    const user = userEvent.setup()
    mocks.patch.mockRejectedValue(failed(500))
    renderPage()
    const box = await screen.findByRole('checkbox', { name: /Riepilogo via email dei documenti da rivedere/ })
    await user.click(box)
    expect(await screen.findByText('Preferenza non salvata')).toBeInTheDocument()
    expect(box).toBeChecked()
  })

  it('reads in English', async () => {
    renderPage('en')
    expect(screen.getByRole('heading', { level: 1, name: 'Check' })).toBeInTheDocument()
    expect(screen.getByText('Check the legal references in your documents against the text in force.')).toBeInTheDocument()
    expect(screen.getByRole('complementary', { name: 'The document is not stored' })).toBeInTheDocument()
    const table = await screen.findByRole('table')
    const gdpr = within(table).getByRole('link', { name: 'Procedura violazioni dati personali.docx' }).closest('tr') as HTMLElement
    expect(within(gdpr).getByText('To correct')).toBeInTheDocument()
    expect(within(gdpr).getByText('2 to correct, 1 to check, 4 fine, 1 not covered')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /To review/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Check the document' })).toBeInTheDocument()
  })
})
