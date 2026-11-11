import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ToastProvider } from '@/components/ui/Toast'
import { renderWithIntl } from '@/test/i18n'
import { ApiError } from '@/lib/api-error'
import { DEMO_CLIENTS } from '@/lib/mock-data'
import { DEMO_DOCUMENTS, demoDocumentsRoute, demoReportHtml, resetDemoDocuments } from '@/lib/mock-documents'

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  del: vi.fn(),
  fetchBlob: vi.fn(),
  push: vi.fn(),
  download: vi.fn(),
  state: { demo: false, id: 'demo-doc-gdpr' },
}))

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mocks.push, replace: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
  usePathname: () => `/app/controlla/${mocks.state.id}`,
  useParams: () => ({ id: mocks.state.id }),
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
  api: { get: mocks.get, post: mocks.post, del: mocks.del, fetchBlob: mocks.fetchBlob },
}))

vi.mock('@/components/report/report-api', () => ({ downloadBlob: mocks.download }))

import { CheckDetailPage } from '../CheckDetailPage'
import { forgetCheck, rememberCheck } from '../documents-api'
import { reportFilename, withLinksInNewTab } from '../ReportDialog'
import type { DocumentCheck } from '../types'

const doc = (id: string): DocumentCheck => DEMO_DOCUMENTS.find((d) => d.id === id) as DocumentCheck

function serve(path: string): unknown {
  if (path.startsWith('/api/v1/clients')) return DEMO_CLIENTS
  const answer = demoDocumentsRoute('GET', path)
  if (answer.handled) return answer.value
  throw new Error(`unexpected GET ${path}`)
}

const failed = (status: number, detail?: string) => new ApiError('requestFailed', { detail, values: { status: String(status) } })

function renderPage(id = 'demo-doc-gdpr', language: 'it' | 'en' = 'it') {
  mocks.state.id = id
  return renderWithIntl(
    <ToastProvider>
      <CheckDetailPage />
    </ToastProvider>,
    { language },
  )
}

describe('CheckDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    resetDemoDocuments()
    forgetCheck()
    mocks.state.demo = false
    mocks.get.mockImplementation(async (path: string) => serve(path))
  })

  it('shows the four groups with their counts and the findings of each, worst first', async () => {
    renderPage()
    expect(await screen.findByRole('heading', { level: 1, name: 'Procedura violazioni dati personali.docx' })).toBeInTheDocument()
    expect(screen.getByText('Controllato il 11 novembre 2026. Data del documento: 12 gennaio 2026.')).toBeInTheDocument()
    expect(mocks.get).toHaveBeenCalledWith('/api/v1/documents/checks/demo-doc-gdpr')

    // The summary: four groups, each with its count; a group with findings leads to its section.
    const summary = screen.getByRole('navigation', { name: 'Esito per gruppo' })
    const tiles = within(summary).getAllByRole('listitem')
    expect(tiles.map((tile) => tile.textContent)).toEqual(['2Da correggere', '1Da controllare', '5A posto', '0Non coperto'])
    expect(within(summary).getByRole('link', { name: /Da correggere/ })).toHaveAttribute('href', '#gruppo-correggere')

    const headings = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)
    expect(headings.slice(0, 3)).toEqual(['Da correggere (2)', 'Da controllare (1)', 'A posto (5)'])
    expect(headings).not.toContain('Non coperto (0)')

    // What asks for attention is shown in full.
    const toCorrect = screen.getByRole('region', { name: 'Da correggere (2)' })
    expect(within(toCorrect).getByRole('article', { name: 'GDPR, art. 33, par. 1' })).toBeInTheDocument()
    expect(within(toCorrect).getByRole('article', { name: 'GDPR, art. 33, par. 6' })).toBeInTheDocument()
    expect(within(toCorrect).getByText('Parole diverse')).toBeInTheDocument()
    const toCheck = screen.getByRole('region', { name: 'Da controllare (1)' })
    expect(within(toCheck).getByRole('article', { name: 'GDPR, art. 28, par. 3' })).toBeInTheDocument()

    // What is fine is one line per reference, open on request.
    const fine = screen.getByRole('region', { name: 'A posto (5)' })
    expect(within(fine).queryByRole('article')).not.toBeInTheDocument()
    expect(fine.querySelectorAll('details')).toHaveLength(5)
    expect(within(fine).getAllByText('Citazione verificata')).toHaveLength(2)
    // Italian law is read on Normattiva: the article of the privacy code is found in the text in force.
    expect(within(fine).getByText('D.Lgs. 196/2003 (Codice privacy), art. 154')).toBeInTheDocument()

    expect(screen.getByText(/I testi consolidati di EUR-Lex sono documentazione: fa fede solo la Gazzetta ufficiale/)).toBeInTheDocument()
  })

  it('keeps the facts of the document and the provisions it depends on in the margin', async () => {
    renderPage()
    const margin = await screen.findByRole('complementary', { name: 'Documento' })
    expect(within(margin).getByText('11 novembre 2026')).toBeInTheDocument()
    expect(within(margin).getByText('12 gennaio 2026')).toBeInTheDocument()
    expect(await within(margin).findByRole('link', { name: 'Beta Software S.r.l.' })).toHaveAttribute('href', '/app/clienti/demo-c2')
    expect(within(margin).getByText('Italiano')).toBeInTheDocument()
    expect(within(margin).getByText('Attiva')).toBeInTheDocument()
    expect(within(margin).getByText(doc('demo-doc-gdpr').document_sha256)).toBeInTheDocument()
    expect(within(margin).getByText(/Il documento non è conservato/)).toBeInTheDocument()

    expect(within(margin).getByRole('heading', { name: 'Norme da cui dipende (5)' })).toBeInTheDocument()
    expect(within(margin).getByText('Vengono ricontrollate ogni settimana sul testo vigente.')).toBeInTheDocument()
    expect(within(margin).getByText('GDPR, Art. 33')).toBeInTheDocument()
    expect(within(margin).getAllByText('Controllata sul testo consolidato al 4 maggio 2016')).toHaveLength(4)
    expect(within(margin).getAllByText('Invariata')).toHaveLength(5)
    expect(within(margin).getByText('D.Lgs. 196/2003 (Codice privacy), Art. 154')).toBeInTheDocument()
    expect(within(margin).getAllByRole('link', { name: /EUR-Lex/ })[0]).toHaveAttribute(
      'href',
      'https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:32016R0679',
    )
  })

  it('says which provisions changed when a check is to review, and no longer calls them verified', async () => {
    const user = userEvent.setup()
    renderPage('demo-doc-csddd')
    const notice = await screen.findByRole('region', { name: 'Da rivedere' })
    expect(notice).toHaveTextContent(
      'Dopo il controllo del 16 febbraio 2026 sono cambiate 3 norme citate. Qui sotto, i riferimenti a quelle norme mostrano che cosa è cambiato.',
    )
    const items = within(notice).getAllByRole('listitem')
    expect(items.map((item) => item.textContent)).toEqual([
      'CSDDD, Art. 2Cambiatarilevato il 23 marzo 2026EUR-Lex',
      'CSDDD, Art. 10Cambiatarilevato il 23 marzo 2026EUR-Lex',
      'CSDDD, Art. 37Cambiatarilevato il 23 marzo 2026EUR-Lex',
    ])
    expect(within(notice).getByRole('link', { name: 'Controlla la versione aggiornata' })).toHaveAttribute(
      'href',
      '/app/controlla?cliente=demo-c6',
    )

    // The margin tells the same story, provision by provision.
    const margin = screen.getByRole('complementary', { name: 'Documento' })
    expect(within(margin).getAllByText('Cambiata')).toHaveLength(3)
    expect(within(margin).getAllByText('Invariata')).toHaveLength(1)

    expect(within(margin).getAllByText('oggi vale il testo consolidato al 18 marzo 2026')).toHaveLength(3)

    // The references to the changed articles are to correct, each with what changed;
    // the quote of article 2, verified on the text of that day, is no longer called verified.
    const toFix = screen.getByRole('region', { name: 'Da correggere (3)' })
    const card = within(toFix).getByRole('article', { name: 'CSDDD, art. 2, par. 1' })
    expect(within(card).getByText('Cambiato dopo il controllo')).toBeInTheDocument()
    expect(
      within(card).getByText(
        "Dopo il controllo questa norma è cambiata: oggi vale il testo consolidato al 18 marzo 2026. L'esito e la citazione qui sotto sono quelli del controllo, sul testo consolidato al 17 aprile 2025.",
      ),
    ).toBeInTheDocument()
    expect(within(card).getByText('Che cosa è cambiato')).toBeInTheDocument()
    expect(within(card).queryByText('Verificata')).not.toBeInTheDocument()
    expect(within(toFix).getAllByRole('article')).toHaveLength(3)
    // Article 14 did not change: its reference stays among those in order.
    const fine = screen.getByRole('region', { name: 'A posto (1)' })
    await user.click(within(fine).getByText('CSDDD, art. 14'))
    expect(within(fine).queryByText(/Dopo il controllo questa norma/)).not.toBeInTheDocument()
  })

  it('tells when a check is not watched and has no client', async () => {
    renderPage('demo-doc-clause')
    const margin = await screen.findByRole('complementary', { name: 'Documento' })
    expect(within(margin).getByText('Non attiva (scelta al momento del controllo)')).toBeInTheDocument()
    expect(within(margin).getByText('Nessuno')).toBeInTheDocument()
    expect(within(margin).getByText('Inglese')).toBeInTheDocument()
    expect(within(margin).getByText('Non indicata')).toBeInTheDocument()
    expect(within(margin).getByText('Non vengono ricontrollate in automatico: puoi farlo tu con «Ricontrolla le norme citate».')).toBeInTheDocument()
    expect(screen.getByText('Controllato il 21 ottobre 2026. Data del documento non indicata.')).toBeInTheDocument()
    // Nothing to correct or to check: only the group that has findings gets a section.
    expect(screen.queryByRole('region', { name: /Da correggere/ })).not.toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'A posto (3)' })).toBeInTheDocument()
  })

  it('re-checks the cited provisions and reports what it found', async () => {
    const user = userEvent.setup()
    const before = doc('demo-doc-ai')
    const after: DocumentCheck = {
      ...before,
      needs_review: true,
      dependencies: before.dependencies.map((d, i) =>
        i === 0 ? { ...d, state: 'changed', changed_at: '2026-11-11T08:00:00Z' } : i === 1 ? { ...d, state: 'unavailable' } : d,
      ),
    }
    mocks.post.mockResolvedValue(after)
    renderPage('demo-doc-ai')
    await user.click(await screen.findByRole('button', { name: 'Ricontrolla le norme citate' }))

    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/v1/documents/checks/demo-doc-ai/recheck', {}))
    expect(await screen.findByText('Ricontrollo completato')).toBeInTheDocument()
    expect(
      screen.getByText(
        'È cambiata una norma citata: il documento è da rivedere. Una norma non è stata ricontrollata: il testo ufficiale non era raggiungibile.',
      ),
    ).toBeInTheDocument()
    // The page now shows the check as the server returned it.
    expect(screen.getByRole('region', { name: 'Da rivedere' })).toHaveTextContent('è cambiata una norma citata')
    const margin = screen.getByRole('complementary', { name: 'Documento' })
    expect(within(margin).getByText('Non ricontrollata: testo ufficiale non raggiungibile')).toBeInTheDocument()
  })

  it('says when nothing changed, and when the re-check failed', async () => {
    const user = userEvent.setup()
    mocks.post.mockResolvedValueOnce(doc('demo-doc-gdpr')).mockRejectedValueOnce(failed(504))
    renderPage()
    await user.click(await screen.findByRole('button', { name: 'Ricontrolla le norme citate' }))
    expect(await screen.findByText('Nessuna delle 5 norme citate è cambiata.')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Ricontrolla le norme citate' }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Ricontrollo non riuscito')
    expect(alert).toHaveTextContent('Il controllo ha superato il tempo massimo prima di finire.')
    expect(alert).toHaveTextContent('Codice 504')
  })

  it('deletes a check only after a confirmation that says what goes', async () => {
    const user = userEvent.setup()
    mocks.del.mockResolvedValue(undefined)
    renderPage()
    await user.click(await screen.findByRole('button', { name: 'Elimina' }))

    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByRole('heading', { name: 'Elimina il controllo' })).toBeInTheDocument()
    expect(dialog).toHaveTextContent('Vuoi eliminare il controllo di Procedura violazioni dati personali.docx?')
    expect(dialog).toHaveTextContent('Il file non è mai stato conservato. L\'operazione non si può annullare.')
    expect(mocks.del).not.toHaveBeenCalled()

    await user.click(within(dialog).getByRole('button', { name: 'Annulla' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(mocks.del).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Elimina' }))
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Elimina il controllo' }))
    await waitFor(() => expect(mocks.del).toHaveBeenCalledWith('/api/v1/documents/checks/demo-doc-gdpr'))
    expect(await screen.findByText('Controllo eliminato')).toBeInTheDocument()
    expect(mocks.push).toHaveBeenCalledWith('/app/controlla')
  })

  it('keeps the dialog open and explains when the deletion fails', async () => {
    const user = userEvent.setup()
    mocks.del.mockRejectedValue(new ApiError('network'))
    renderPage()
    await user.click(await screen.findByRole('button', { name: 'Elimina' }))
    const dialog = screen.getByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Elimina il controllo' }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Il server non risponde.')
    expect(mocks.push).not.toHaveBeenCalled()
  })

  it('opens the HTML report in a frame that cannot run scripts, and offers it as a file', async () => {
    const user = userEvent.setup()
    const html = demoReportHtml(doc('demo-doc-gdpr'))
    mocks.fetchBlob.mockResolvedValue(new Response(html, { headers: { 'Content-Type': 'text/html' } }))
    renderPage()
    await user.click(await screen.findByRole('button', { name: 'Apri il report' }))

    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByRole('heading', { name: 'Report del controllo' })).toBeInTheDocument()
    const frame = await within(dialog).findByTitle('Report del controllo di Procedura violazioni dati personali.docx')
    expect(mocks.fetchBlob).toHaveBeenCalledWith('/api/v1/documents/checks/demo-doc-gdpr/report')
    expect(frame.tagName).toBe('IFRAME')
    // No allow-scripts and no allow-same-origin: the page of the server cannot reach the session.
    expect(frame).toHaveAttribute('sandbox', 'allow-popups allow-popups-to-escape-sandbox')
    expect(frame.getAttribute('srcdoc')).toContain('<base target="_blank">')
    expect(frame.getAttribute('srcdoc')).toContain('Procedura violazioni dati personali.docx')

    await user.click(within(dialog).getByRole('button', { name: 'Scarica il report (.html)' }))
    expect(mocks.download).toHaveBeenCalledTimes(1)
    const [blob, filename] = mocks.download.mock.calls[0] as [Blob, string]
    expect(filename).toBe('Procedura violazioni dati personali.controllo.html')
    expect(blob.type).toContain('text/html')
    expect(await blob.text()).toBe(html)
  })

  it('says when the report did not load and tries again', async () => {
    const user = userEvent.setup()
    mocks.fetchBlob.mockRejectedValueOnce(failed(500)).mockResolvedValueOnce(new Response('<!doctype html><html><head></head><body>ok</body></html>'))
    renderPage()
    await user.click(await screen.findByRole('button', { name: 'Apri il report' }))
    const dialog = screen.getByRole('dialog')
    const alert = await within(dialog).findByRole('alert')
    expect(alert).toHaveTextContent('Il report non si è caricato')
    expect(within(dialog).getByRole('button', { name: 'Scarica il report (.html)' })).toBeDisabled()
    await user.click(within(alert).getByRole('button', { name: 'Riprova il caricamento' }))
    expect(await within(dialog).findByTitle(/Report del controllo di/)).toBeInTheDocument()
  })

  it('says when the check does not exist, and when it could not be loaded', async () => {
    const user = userEvent.setup()
    const missing = renderPage('nope')
    expect(await screen.findByText('Controllo non trovato')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Vai ai documenti controllati' })).toHaveAttribute('href', '/app/controlla')
    missing.unmount()

    mocks.get.mockRejectedValueOnce(failed(503, 'Il database non è raggiungibile.')).mockImplementation(async (path: string) => serve(path))
    renderPage()
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Il controllo non si è caricato')
    expect(alert).toHaveTextContent('Il server ha avuto un problema.')
    expect(alert).toHaveTextContent('Dal server: Il database non è raggiungibile.')
    expect(alert).toHaveTextContent('Codice 503')
    await user.click(within(alert).getByRole('button', { name: 'Riprova il caricamento' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Procedura violazioni dati personali.docx' })).toBeInTheDocument()
  })

  it('reads the check the form just received instead of asking the server again', async () => {
    rememberCheck(doc('demo-doc-ai'), false)
    renderPage('demo-doc-ai')
    expect(await screen.findByRole('heading', { level: 1, name: 'Policy uso IA.pdf' })).toBeInTheDocument()
    expect(mocks.get).not.toHaveBeenCalledWith('/api/v1/documents/checks/demo-doc-ai')
    expect(screen.getByRole('article', { name: 'AI Act, art. 4' })).toBeInTheDocument()
    expect(screen.getByText('Che cosa è cambiato')).toBeInTheDocument()
  })

  it('declares the demo on the page of a check, and after an upload says the file was not read', async () => {
    mocks.state.demo = true
    const plain = renderPage()
    expect(
      await screen.findByText(
        'Demo con dati di esempio: il documento, il cliente e le date sono inventati. I passaggi di legge sono quelli ufficiali.',
      ),
    ).toBeInTheDocument()
    plain.unmount()

    rememberCheck(doc('demo-doc-gdpr'), true)
    renderPage()
    expect(
      await screen.findByText(
        'Demo con dati di esempio: il documento che hai scelto non è stato letto né inviato. Questo è il risultato di un documento di esempio.',
      ),
    ).toBeInTheDocument()
  })

  it('says in the demo that the re-check read nothing', async () => {
    const user = userEvent.setup()
    mocks.state.demo = true
    mocks.post.mockResolvedValue(doc('demo-doc-gdpr'))
    renderPage()
    await user.click(await screen.findByRole('button', { name: 'Ricontrolla le norme citate' }))
    expect(
      await screen.findByText(
        'Nessuna delle 5 norme citate è cambiata. Demo con dati di esempio: nessun testo ufficiale è stato riletto.',
      ),
    ).toBeInTheDocument()
  })

  it('reads in English, with the law in the language of the document', async () => {
    renderPage('demo-doc-ai', 'en')
    expect(await screen.findByRole('heading', { level: 1, name: 'Policy uso IA.pdf' })).toBeInTheDocument()
    expect(screen.getByText('Checked on 4 November 2026. Date of the document: 15 March 2026.')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'To correct (1)' })).toBeInTheDocument()
    expect(screen.getByText('Outdated quote')).toBeInTheDocument()
    expect(screen.getByText('From the original text to the consolidated text of 27 July 2026.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Re-check the cited provisions' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Provisions it depends on (4)' })).toBeInTheDocument()
  })
})

describe('the report helpers', () => {
  it('make every link of the report open in a new tab', () => {
    expect(withLinksInNewTab('<!doctype html><html lang="it"><head><meta charset="utf-8"></head><body></body></html>')).toBe(
      '<!doctype html><html lang="it"><head><base target="_blank"><meta charset="utf-8"></head><body></body></html>',
    )
    expect(withLinksInNewTab('<p>solo testo</p>')).toBe('<base target="_blank"><p>solo testo</p>')
  })

  it('name the file after the document', () => {
    expect(reportFilename('Policy uso IA.pdf', 'controllo')).toBe('Policy uso IA.controllo.html')
    expect(reportFilename('nota: bozza?.docx', 'check')).toBe('nota_ bozza_.check.html')
    expect(reportFilename('', 'controllo')).toBe('report.controllo.html')
  })
})
