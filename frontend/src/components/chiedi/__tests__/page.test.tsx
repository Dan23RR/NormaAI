import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ToastProvider } from '@/components/ui/Toast'
import { renderWithIntl } from '@/test/i18n'

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  replace: vi.fn(),
}))

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: mocks.replace, push: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
  usePathname: () => '/app/chiedi',
}))

vi.mock('@/lib/auth', () => ({
  isDemoMode: () => true,
  getAccessToken: () => 'demo.jwt.token',
}))

vi.mock('@/lib/api', () => ({
  api: { post: (...args: unknown[]) => mocks.post(...args), getBaseUrl: () => '' },
}))

import { ChiediPage } from '../ChiediPage'

// happy-dom does not expose the storages as globals: give the page the same
// in-memory ones the test reads back.
function memoryStorage(): Storage {
  const store: Record<string, string> = {}
  return {
    getItem: (key: string) => (key in store ? store[key] : null),
    setItem: (key: string, value: string) => {
      store[key] = String(value)
    },
    removeItem: (key: string) => {
      delete store[key]
    },
    clear: () => {
      for (const k of Object.keys(store)) delete store[k]
    },
    key: (i: number) => Object.keys(store)[i] ?? null,
    get length() {
      return Object.keys(store).length
    },
  }
}
vi.stubGlobal('sessionStorage', memoryStorage())
vi.stubGlobal('localStorage', memoryStorage())

const ANSWER = {
  status: 'success',
  data: {
    answer:
      "Sì. L'articolo 50, paragrafo 1, del Regolamento (UE) 2024/1689 obbliga chi fornisce un chatbot a dirlo [1]. L'obbligo si applica dal 2 agosto 2026 [2].",
    citations: [
      { framework: 'AI_ACT', reference: 'art. 50, par. 1', quote_snippet: 'siano informate del fatto che stanno interagendo con un sistema di IA', celex: '32024R1689', verified: true },
      { framework: 'AI_ACT', reference: 'art. 113', quote_snippet: 'Esso si applica a decorrere dal 2 agosto 2026.', celex: '32024R1689' },
    ],
    confidence_score: 0.94,
    requires_expert_review: false,
    related_frameworks: ['GDPR'],
    caveats: ['Per le PMI si applica il minore dei due importi.'],
  },
  metadata: { timestamp: '2026-10-23T10:00:00Z', model: 'demo-mode', corpus_as_of: '2026-02-28' },
}

function renderPage(language: 'it' | 'en' = 'it') {
  return renderWithIntl(
    <ToastProvider>
      <ChiediPage />
    </ToastProvider>,
    { language },
  )
}

describe('ChiediPage (demo mode)', () => {
  beforeEach(() => {
    sessionStorage.clear()
    localStorage.clear()
    mocks.post.mockReset()
    mocks.replace.mockReset()
  })

  it('sends a question and shows the answer with its sources in the margin', async () => {
    mocks.post.mockResolvedValue(ANSWER)
    const user = userEvent.setup()
    renderPage()

    expect(screen.getByRole('heading', { name: 'Chiedi' })).toBeInTheDocument()
    expect(screen.getByText('Cosa vuoi sapere?')).toBeInTheDocument()

    await user.type(screen.getByLabelText('La tua domanda'), 'Un chatbot deve dichiarare di essere un’IA?')
    await user.click(screen.getByRole('button', { name: 'Invia la domanda' }))

    expect(mocks.post).toHaveBeenCalledTimes(1)
    const [path, body] = mocks.post.mock.calls[0] as [string, { question: string; language: string; company_profile?: { name: string } }]
    expect(path).toBe('/api/v1/qa')
    expect(body.question).toBe('Un chatbot deve dichiarare di essere un’IA?')
    expect(body.language).toBe('it')
    expect(body.company_profile?.name).toBe('Acme Srl')

    // The question is shown as a turn, the answer arrives with its markers.
    expect(screen.getByText('Un chatbot deve dichiarare di essere un’IA?')).toBeInTheDocument()
    await screen.findByText(/Sì\. L'articolo 50, paragrafo 1/)
    expect(screen.getByRole('button', { name: 'Vai alla fonte 1' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Vai alla fonte 2' })).toBeInTheDocument()

    // The sources margin lists both sources with their honest status.
    const margin = screen.getByRole('complementary', { name: 'Fonti e profilo' })
    expect(within(margin).getByRole('heading', { name: 'Fonti (2)' })).toBeInTheDocument()
    expect(within(margin).getAllByText('Regolamento (UE) 2024/1689 (AI Act)')).toHaveLength(2)
    expect(within(margin).getByText('art. 50, par. 1')).toBeInTheDocument()
    expect(within(margin).getByText('siano informate del fatto che stanno interagendo con un sistema di IA')).toBeInTheDocument()
    expect(within(margin).getByText('Verificata')).toBeInTheDocument()
    expect(within(margin).getByText('Da verificare')).toBeInTheDocument()
    expect(within(margin).getAllByRole('link', { name: /EUR-Lex/ })[0]).toHaveAttribute(
      'href',
      'https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:32024R1689',
    )

    // Confidence as a label, never the number; caveats; related frameworks; AI notice; corpus date.
    expect(screen.getByText('Alta affidabilità')).toBeInTheDocument()
    expect(screen.queryByText('0.94')).not.toBeInTheDocument()
    expect(screen.getByText('Per le PMI si applica il minore dei due importi.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Chiedi di GDPR' })).toBeInTheDocument()
    expect(screen.getAllByText(/Risposta generata da un sistema di IA\./).length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText(/Corpus al 28 febbraio 2026/).length).toBeGreaterThanOrEqual(2)
    expect(screen.getByRole('button', { name: 'Copia con fonti' })).toBeInTheDocument()

    // Under lg the same sources sit under the answer, collapsed.
    const toggle = screen.getByRole('button', { name: 'Fonti (2)' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await user.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')

    // A related framework prefills a follow-up question.
    await user.click(screen.getByRole('button', { name: 'Chiedi di GDPR' }))
    expect(screen.getByLabelText('La tua domanda')).toHaveValue(
      'Quali sono gli obblighi principali previsti da GDPR per la nostra azienda?',
    )

    // The conversation is kept for the tab.
    const stored = JSON.parse(sessionStorage.getItem('normaai_qa_messages') ?? '[]')
    expect(stored).toHaveLength(2)
    expect(stored[1].data.citations).toHaveLength(2)
  })

  it('follows the interface language: English words, English answer language, English EUR-Lex link', async () => {
    mocks.post.mockResolvedValue(ANSWER)
    const user = userEvent.setup()
    renderPage('en')

    expect(screen.getByRole('heading', { name: 'Ask' })).toBeInTheDocument()
    expect(screen.getByText('What do you want to know?')).toBeInTheDocument()
    expect(screen.getByLabelText('Answer language')).toHaveValue('en')

    await user.type(screen.getByLabelText('Your question'), 'Does a chatbot have to say it is an AI?')
    await user.click(screen.getByRole('button', { name: 'Send the question' }))

    const [, body] = mocks.post.mock.calls[0] as [string, { language: string }]
    expect(body.language).toBe('en')

    await screen.findByText(/Sì\. L'articolo 50, paragrafo 1/)
    const margin = screen.getByRole('complementary', { name: 'Sources and profile' })
    expect(within(margin).getByRole('heading', { name: 'Sources (2)' })).toBeInTheDocument()
    expect(within(margin).getAllByText('Regulation (EU) 2024/1689 (AI Act)')).toHaveLength(2)
    expect(within(margin).getByText('Verified')).toBeInTheDocument()
    expect(within(margin).getByText('Unverified')).toBeInTheDocument()
    expect(within(margin).getAllByRole('link', { name: /EUR-Lex/ })[0]).toHaveAttribute(
      'href',
      'https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1689',
    )
    expect(screen.getByText('High reliability')).toBeInTheDocument()
    expect(screen.getAllByText(/Corpus as of 28 February 2026/).length).toBeGreaterThanOrEqual(2)
    expect(screen.getByRole('button', { name: 'Copy with sources' })).toBeInTheDocument()
  })

  it('renders an abstention instead of an answer', async () => {
    mocks.post.mockResolvedValue({
      status: 'success',
      data: {
        answer: 'Non posso fornire una risposta sufficientemente affidabile su questa domanda.',
        citations: [],
        confidence_score: 0.2,
        requires_expert_review: true,
        abstention_reason: 'snc_low_trust',
      },
      metadata: {},
    })
    const user = userEvent.setup()
    renderPage()
    await user.type(screen.getByLabelText('La tua domanda'), 'Quanto costa un caffè a Bruxelles?')
    await user.keyboard('{Enter}')

    await screen.findByText('NormaAI non risponde a questa domanda')
    expect(screen.getByText(/Non posso fornire una risposta sufficientemente affidabile/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Apri EUR-Lex/ })).toBeInTheDocument()
    expect(screen.queryByText('Alta affidabilità')).not.toBeInTheDocument()
    expect(screen.queryByText('Richiede verifica')).not.toBeInTheDocument()
    expect(screen.queryByText(/Corpus al/)).not.toBeInTheDocument()
  })

  it('shows an honest error with a retry that asks again', async () => {
    mocks.post.mockRejectedValueOnce(new Error('Il server non risponde. Riprova tra un minuto.')).mockResolvedValueOnce(ANSWER)
    const user = userEvent.setup()
    renderPage()
    await user.type(screen.getByLabelText('La tua domanda'), 'Quali incidenti vanno notificati entro 24 ore secondo la NIS2?')
    await user.keyboard('{Enter}')

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Il server non risponde. Riprova tra un minuto.')
    await user.click(within(alert).getByRole('button', { name: 'Riprova' }))
    await waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(2))
    await screen.findByText(/Sì\. L'articolo 50, paragrafo 1/)
  })

  it('starts a new conversation and clears the storage', async () => {
    mocks.post.mockResolvedValue(ANSWER)
    const user = userEvent.setup()
    renderPage()
    await user.type(screen.getByLabelText('La tua domanda'), 'Domanda di prova sulla NIS2')
    await user.keyboard('{Enter}')
    await screen.findByText(/Sì\. L'articolo 50, paragrafo 1/)

    await user.click(screen.getByRole('button', { name: 'Nuova conversazione' }))
    expect(screen.getByText('Cosa vuoi sapere?')).toBeInTheDocument()
    expect(sessionStorage.getItem('normaai_qa_messages')).toBeNull()
  })
})
