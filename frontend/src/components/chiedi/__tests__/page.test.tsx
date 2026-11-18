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
      { framework: 'AI_ACT', reference: 'art. 50, par. 1', quote_snippet: 'siano informate del fatto di stare interagendo con un sistema di IA', celex: '32024R1689', verified: true },
      { framework: 'AI_ACT', reference: 'art. 113', quote_snippet: 'Si applica a decorrere dal 2 agosto 2026.', celex: '32024R1689' },
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
    expect(within(margin).getByText('siano informate del fatto di stare interagendo con un sistema di IA')).toBeInTheDocument()
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

  it('asks a suggested question with one click', async () => {
    mocks.post.mockResolvedValue(ANSWER)
    const user = userEvent.setup()
    renderPage()

    const suggestions = within(screen.getByRole('list', { name: 'Esempi di domande' })).getAllByRole('button')
    expect(suggestions).toHaveLength(3)
    const question = suggestions[1].textContent as string
    await user.click(suggestions[1])

    // No second click on "Invia la domanda": the question is already on its way.
    expect(mocks.post).toHaveBeenCalledTimes(1)
    const [path, body] = mocks.post.mock.calls[0] as [string, { question: string; language: string }]
    expect(path).toBe('/api/v1/qa')
    expect(body.question).toBe(question)
    expect(body.language).toBe('it')
    expect(screen.getByLabelText('La tua domanda')).toHaveValue('')
    expect(screen.getByText(question)).toBeInTheDocument()
    await screen.findByText(/Sì\. L'articolo 50, paragrafo 1/)
    expect(screen.queryByText('Cosa vuoi sapere?')).not.toBeInTheDocument()
  })

  it('asks an example question of an abstention with one click', async () => {
    mocks.post
      .mockResolvedValueOnce({
        status: 'success',
        data: {
          answer: 'La demo copre alcuni scenari di esempio.',
          citations: [],
          confidence_score: 0,
          requires_expert_review: false,
          abstention_reason: 'demo_not_covered',
          suggested_questions: ['Quali incidenti vanno notificati entro 24 ore secondo la NIS2?'],
        },
        metadata: {},
      })
      .mockResolvedValueOnce(ANSWER)
    const user = userEvent.setup()
    renderPage()
    await user.type(screen.getByLabelText('La tua domanda'), 'Quanto costa un caffè a Bruxelles?')
    await user.keyboard('{Enter}')
    await screen.findByText('NormaAI non risponde a questa domanda')

    await user.click(screen.getByRole('button', { name: 'Quali incidenti vanno notificati entro 24 ore secondo la NIS2?' }))
    await waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(2))
    const [, body] = mocks.post.mock.calls[1] as [string, { question: string }]
    expect(body.question).toBe('Quali incidenti vanno notificati entro 24 ore secondo la NIS2?')
    await screen.findByText(/Sì\. L'articolo 50, paragrafo 1/)
  })

  it('shows in the margin that a quote differs from the official text, and how', async () => {
    mocks.post.mockResolvedValue({
      status: 'success',
      data: {
        answer: 'La violazione va notificata entro 48 ore [1].',
        citations: [
          {
            framework: 'GDPR',
            reference: 'art. 33, par. 1',
            quote_snippet: 'senza ingiustificato ritardo e, ove possibile, entro 48 ore dal momento in cui ne è venuto a conoscenza',
            celex: '32016R0679',
            verified: false,
            near_quote: 'senza ingiustificato ritardo e, ove possibile, entro 72 ore dal momento in cui ne è venuto a conoscenza',
            near_article: 'Art. 33',
            differences: [{ quoted: '48', official: '72' }],
          },
        ],
        confidence_score: 0.4,
        requires_expert_review: true,
        related_frameworks: [],
        caveats: [],
      },
      metadata: {},
    })
    const user = userEvent.setup()
    renderPage()
    await user.type(screen.getByLabelText('La tua domanda'), 'Entro quando va notificata una violazione dei dati?')
    await user.keyboard('{Enter}')
    await screen.findByText(/La violazione va notificata entro 48 ore/)

    const margin = screen.getByRole('complementary', { name: 'Fonti e profilo' })
    expect(within(margin).getByText('Regolamento (UE) 2016/679 (GDPR)')).toBeInTheDocument()
    expect(within(margin).getByText('Da verificare')).toBeInTheDocument()
    expect(within(margin).queryByText('Verificata')).not.toBeInTheDocument()

    // It differs, this is how, and this is what the official text says.
    expect(within(margin).getByText('Diversa dal testo ufficiale')).toBeInTheDocument()
    expect(
      within(margin).getByText(
        'Nella risposta: «senza ingiustificato ritardo e, ove possibile, entro 48 ore dal momento in cui ne è venuto a conoscenza»',
      ),
    ).toBeInTheDocument()
    expect(within(margin).getByText('Testo ufficiale, Art. 33')).toBeInTheDocument()
    const note = within(margin).getByText('Diversa dal testo ufficiale').parentElement as HTMLElement
    expect(within(note).getByRole('listitem')).toHaveTextContent('Nella risposta «48», nel testo ufficiale «72».')

    // The highlighter marks the official words only, never the altered quote.
    const marks = margin.querySelectorAll('mark')
    expect(marks).toHaveLength(1)
    expect(marks[0]).toHaveTextContent(/^72$/)
    expect(marks[0].parentElement).toHaveTextContent(
      'senza ingiustificato ritardo e, ove possibile, entro 72 ore dal momento in cui ne è venuto a conoscenza',
    )
  })

  it('shows a quote found in another act as not verified, with where it really is', async () => {
    const quote = 'garantiscono che gli output del sistema di IA siano marcati'
    mocks.post.mockResolvedValue({
      status: 'success',
      data: {
        answer: 'Gli output vanno marcati [GDPR, Art. 6].',
        citations: [
          {
            framework: 'GDPR',
            reference: 'Art. 6',
            quote_snippet: quote,
            verified: false,
            found_elsewhere: true,
            found_in: 'act',
            found_celex: '32024R1689',
            found_article: 'Art. 50',
            found_paragraph: '2',
            found_quote: quote,
            found_url: 'https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:32024R1689',
          },
        ],
        confidence_score: 0.6,
        requires_expert_review: true,
        related_frameworks: [],
        caveats: [
          'La citazione [GDPR, Art. 6] non è verificata: il testo citato si trova in un altro atto, Regolamento (UE) 2024/1689, Art. 50, par. 2.',
        ],
      },
      metadata: {},
    })
    const user = userEvent.setup()
    renderPage()
    await user.type(screen.getByLabelText('La tua domanda'), 'Gli output di un sistema di IA vanno marcati?')
    await user.keyboard('{Enter}')
    await screen.findByText(/Gli output vanno marcati/)

    const margin = screen.getByRole('complementary', { name: 'Fonti e profilo' })
    expect(within(margin).getByText('Regolamento (UE) 2016/679 (GDPR)')).toBeInTheDocument()
    expect(within(margin).getByText('Da verificare')).toBeInTheDocument()
    expect(within(margin).queryByText('Verificata')).not.toBeInTheDocument()
    expect(
      within(margin).getByText('Testo trovato in un altro atto: Regolamento (UE) 2024/1689 (AI Act), Art. 50, par. 2'),
    ).toBeInTheDocument()
    expect(within(margin).getByRole('link', { name: /Apri il testo ufficiale/ })).toHaveAttribute(
      'href',
      'https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:32024R1689',
    )
    // The caveat names the mismatch under the answer too.
    expect(screen.getByText(/La citazione \[GDPR, Art. 6\] non è verificata/)).toBeInTheDocument()
  })

  it('labels an answer the backend marks as AI-generated (AI Act, Art. 50(2))', async () => {
    mocks.post.mockResolvedValue({
      ...ANSWER,
      data: {
        ...ANSWER.data,
        ai_generated: true,
        generator: { system: 'NormaAI Chiedi', provider: 'anthropic', model: 'claude-haiku-5-5' },
      },
    })
    const user = userEvent.setup()
    renderPage()
    await user.type(screen.getByLabelText('La tua domanda'), 'Un chatbot deve dire che è una IA?')
    await user.keyboard('{Enter}')
    const label = await screen.findByText('Testo generato con un sistema di IA')
    expect(label).toHaveAttribute('title', 'Modello: claude-haiku-5-5')
  })

  it('does not label an answer the backend does not mark', async () => {
    mocks.post.mockResolvedValue(ANSWER)
    const user = userEvent.setup()
    renderPage()
    await user.type(screen.getByLabelText('La tua domanda'), 'Un chatbot deve dire che è una IA?')
    await user.keyboard('{Enter}')
    await screen.findByText(/obbliga chi fornisce un chatbot/)
    expect(screen.queryByText('Testo generato con un sistema di IA')).not.toBeInTheDocument()
  })

  it('names an act cited by its CELEX, in the answer and in the margin', async () => {
    mocks.post.mockResolvedValue({
      status: 'success',
      data: {
        answer: 'Il regolamento modifica il calendario [32026R1744, Art. 1].',
        citations: [
          {
            framework: '32026R1744',
            reference: 'Art. 1',
            quote_snippet: 'Il regolamento (UE) 2024/1689 è così modificato',
            verified: true,
            celex: '32026R1744',
            article: 'Art. 1',
            official_quote: 'Il regolamento (UE) 2024/1689 è così modificato',
          },
        ],
        confidence_score: 0.9,
        requires_expert_review: false,
        related_frameworks: [],
        caveats: [],
      },
      metadata: {},
    })
    const user = userEvent.setup()
    renderPage()
    await user.type(screen.getByLabelText('La tua domanda'), 'Cosa cambia il regolamento 2026/1744?')
    await user.keyboard('{Enter}')
    // The marker reads the act's name, not "[32026R1744, Art. 1]", and still leads to its source.
    const marker = await screen.findByRole('button', { name: 'Vai alla fonte 1' })
    expect(marker).toHaveTextContent('[Regolamento (UE) 2026/1744, Art. 1]')
    const margin = screen.getByRole('complementary', { name: 'Fonti e profilo' })
    expect(within(margin).getByText('Regolamento (UE) 2026/1744')).toBeInTheDocument()
    expect(within(margin).getByText('Verificata')).toBeInTheDocument()
  })
})
