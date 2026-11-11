import { describe, it, expect, vi } from 'vitest'
import { screen, within } from '@testing-library/react'
import { renderWithIntl, MESSAGES } from '@/test/i18n'
import { LANGUAGES, LOCALES, type Language } from '@/i18n/config'
import { LONG_DATE, isoToUtcDate } from '@/i18n/format'
import { CORPUS_ACTS, CORPUS_AREAS } from '@/lib/corpus-acts'
import {
  AI_ACT_IN_FORCE,
  ANSWER_DATE_PASSAGE,
  ANSWER_PASSAGE,
  CHANGED_PROVISION,
  CHECKED_NOTE,
  EXAMPLES_CHECKED_ON,
  GDPR_IN_FORCE,
} from '@/lib/landing-examples'
import { eurlexUrl } from '@/lib/sources'

vi.mock('next/link', () => ({
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  default: ({ children, href, ...props }: any) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}))

// The header reads the session from localStorage, which happy-dom does not
// expose as a global: an empty one stands for a visitor who is not signed in.
vi.stubGlobal('localStorage', {
  getItem: () => null,
  setItem: () => undefined,
  removeItem: () => undefined,
  clear: () => undefined,
  key: () => null,
  length: 0,
})

import Home from '@/app/page'

/** A date as the page writes it, with the ICU data of this Node. */
function longDate(iso: string, language: Language): string {
  return new Intl.DateTimeFormat(LOCALES[language], LONG_DATE).format(isoToUtcDate(iso) as Date)
}

/** The words that open the status line: "Stato al 3 dicembre 2026.", "Status on 3 December 2026." */
const STATUS_DATE = {
  it: /^Stato (al |all')\d{1,2} [a-z]+ \d{4}\.$/,
  en: /^Status on \d{1,2} [A-Z][a-z]+ \d{4}\.$/,
}

function renderLanding(language: Language = 'it') {
  return renderWithIntl(<Home />, { language })
}

describe('landing page', () => {
  it('opens with the document check, in the words of the positioning', () => {
    renderLanding()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Controlla i riferimenti di legge dei tuoi documenti sul testo vigente.',
    )
    expect(
      screen.getByText("Norme UE e italiane, parola per parola. Con l'avviso quando una norma citata cambia."),
    ).toBeInTheDocument()
  })

  it('offers two actions that work today: the demo and an email for a pilot', () => {
    renderLanding()
    const main = within(screen.getByRole('main'))
    const demo = main.getAllByRole('link', { name: 'Prova la demo' })
    const pilot = main.getAllByRole('link', { name: 'Scrivi per un pilot' })
    // Once in the hero and once at the bottom of the page.
    expect(demo).toHaveLength(2)
    expect(pilot).toHaveLength(2)
    for (const link of demo) expect(link).toHaveAttribute('href', '/demo')
    for (const link of pilot) expect(link.getAttribute('href')).toMatch(/^mailto:info@normaai\.org\?subject=/)
  })

  it('promises no sign-up and sends nobody to the scope checks from the hero', () => {
    renderLanding()
    const main = within(screen.getByRole('main'))
    const targets = main.getAllByRole('link').map((link) => link.getAttribute('href') ?? '')
    expect(targets.filter((href) => href.startsWith('/login'))).toEqual([])
    // The free checks stay, as plain links of their own section.
    const checks = within(document.getElementById('ambito') as HTMLElement).getAllByRole('link')
    expect(checks.map((link) => link.getAttribute('href'))).toEqual(['/scope-csrd.html', '/scope-aiact.html'])
    expect(targets.filter((href) => href.startsWith('/scope-'))).toHaveLength(2)
  })

  it('says once, with its date, what a visitor cannot reach yet', () => {
    renderLanding()
    // "Stato all'11 novembre 2026.": whatever the day, one dated line and no other.
    const dated = screen.getAllByText(STATUS_DATE.it)
    expect(dated).toHaveLength(1)
    const status = dated[0].parentElement as HTMLElement
    expect(status).toHaveTextContent(/Aperti a tutti: .+ Non ancora aperti: .+/)
    expect(screen.queryByText(/in sviluppo/i)).not.toBeInTheDocument()
  })

  it.each(LANGUAGES)('shows the checked note with the official wording under the highlighter (%s)', (language) => {
    renderLanding(language)
    const note = CHECKED_NOTE[language]
    const figure = screen.getByRole('figure', {
      name: language === 'it' ? 'Esempio di controllo di un documento' : 'Example of a document check',
    })
    const example = within(figure)

    // The date of the check and the text it ran on are on the page.
    expect(figure).toHaveTextContent(longDate(EXAMPLES_CHECKED_ON, language))
    expect(figure).toHaveTextContent(longDate(GDPR_IN_FORCE.asOf as string, language))
    expect(example.getByRole('link', { name: 'EUR-Lex' })).toHaveAttribute(
      'href',
      eurlexUrl(GDPR_IN_FORCE.celex, language === 'it' ? 'IT' : 'EN'),
    )

    // The note keeps its own words, wrong number included; only the law is highlighted.
    expect(figure).toHaveTextContent(note.altered.quote)
    expect(figure).toHaveTextContent(note.verified.quote)
    const marks = Array.from(figure.querySelectorAll('mark'))
    expect(marks.map((mark) => mark.textContent)).toEqual([note.altered.official])
    expect(marks[0].querySelector('strong')?.textContent).toBe(note.altered.difference.official)

    // Both outcomes, in the words of the document check.
    expect(
      example.getByText(language === 'it' ? 'Citazione diversa dal testo ufficiale' : 'Quote differs from the official text'),
    ).toBeInTheDocument()
    expect(example.getByText(language === 'it' ? 'Citazione verificata' : 'Quote verified')).toBeInTheDocument()
    expect(figure).toHaveTextContent(
      language === 'it'
        ? 'nel documento «48», nel testo ufficiale «72».'
        : 'in the document "48", in the official text "72".',
    )
  })

  it.each(LANGUAGES)('keeps the highlighter for official wording only (%s)', (language) => {
    const { container } = renderLanding(language)
    const official = [
      CHECKED_NOTE[language].altered.official,
      CHANGED_PROVISION[language].now,
      ANSWER_PASSAGE[language].quote,
      ANSWER_DATE_PASSAGE[language].quote,
    ]
    const highlighted = Array.from(container.querySelectorAll('mark'), (mark) => mark.textContent)
    expect(highlighted).toEqual(official)
  })

  it('shows the provision that changed, earlier words plain and words in force highlighted', () => {
    renderLanding()
    const figure = screen.getByRole('figure', { name: 'Esempio di una norma citata che è cambiata' })
    expect(figure).toHaveTextContent('Citazione superata')
    expect(figure).toHaveTextContent(CHANGED_PROVISION.it.before)
    expect(figure).toHaveTextContent(longDate(CHANGED_PROVISION.it.documentDate, 'it'))
    expect(figure).toHaveTextContent(longDate(AI_ACT_IN_FORCE.asOf as string, 'it'))
    expect(within(figure).getByRole('link', { name: 'EUR-Lex' })).toHaveAttribute(
      'href',
      eurlexUrl(AI_ACT_IN_FORCE.celex, 'IT'),
    )
  })

  it('marks the passages of the example answer as verified, with the date of the check', () => {
    renderLanding()
    const figure = screen.getByRole('figure', { name: 'Esempio di risposta con i passaggi di legge' })
    expect(within(figure).getAllByText('Verificata')).toHaveLength(2)
    expect(figure).toHaveTextContent(`Data della verifica: ${longDate(EXAMPLES_CHECKED_ON, 'it')}`)
    for (const link of within(figure).getAllByRole('link', { name: 'EUR-Lex' })) {
      expect(link).toHaveAttribute('href', eurlexUrl(AI_ACT_IN_FORCE.celex, 'IT'))
    }
  })

  it.each(LANGUAGES)('lists the acts of the corpus, each linked to EUR-Lex, and no national decree (%s)', (language) => {
    renderLanding(language)
    const table = screen.getByRole('table')
    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows).toHaveLength(CORPUS_AREAS.length)
    const links = within(table).getAllByRole('link')
    expect(links.map((link) => link.getAttribute('href'))).toEqual(
      CORPUS_ACTS.map((act) => eurlexUrl(act.celex, language === 'it' ? 'IT' : 'EN')),
    )
    expect(table).not.toHaveTextContent(/D\.\s?Lgs|Legislative Decree|decreto/i)
    expect(
      screen.getByRole('heading', {
        name: language === 'it' ? `Per le risposte: ${CORPUS_ACTS.length} atti dell'Unione` : `For answers: ${CORPUS_ACTS.length} EU acts`,
      }),
    ).toBeInTheDocument()
  })

  it('counts the areas the way the table shows them', () => {
    renderLanding()
    expect(screen.getByText(new RegExp(`Una persona, ${CORPUS_AREAS.length} ambiti normativi\\.`))).toBeInTheDocument()
  })

  it('leads the audience with the consultants', () => {
    renderLanding()
    const section = screen.getByRole('heading', { name: 'Per chi lavora con documenti che citano la legge.' })
      .parentElement as HTMLElement
    const audiences = within(section).getAllByRole('heading', { level: 3 })
    expect(audiences.map((h) => h.textContent)).toEqual([
      'Consulenti che seguono molte aziende',
      "PMI e titolari d'azienda",
      'Compliance officer e uffici legali',
    ])
  })

  it('keeps the anchors the header, the footer and the /codex redirect point to', () => {
    renderLanding()
    for (const id of ['come-funziona', 'fonti', 'codex', 'demo']) {
      expect(document.getElementById(id), id).not.toBeNull()
    }
  })

  it('keeps the Codex form in place', () => {
    renderLanding()
    const codex = within(document.getElementById('codex') as HTMLElement)
    expect(codex.getByRole('heading', { name: 'Codex Post-Omnibus 2025-2029' })).toBeInTheDocument()
    expect(codex.getByLabelText(/Email di lavoro/)).toBeInTheDocument()
    expect(codex.getByRole('button', { name: 'Scarica il Codex' })).toBeInTheDocument()
  })

  it.each(LANGUAGES)('finds every message it asks for (%s)', (language) => {
    // A missing message is reported on the console and rendered as its own
    // path, e.g. "landing.hero.title".
    const errors = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    try {
      const { container } = renderLanding(language)
      const missing = errors.mock.calls.map((call) => String(call[0])).filter((text) => text.includes('MISSING_MESSAGE'))
      expect(missing).toEqual([])
      expect(container.textContent).not.toMatch(/landing\.[a-zA-Z0-9]+\.[a-zA-Z0-9]+/)
    } finally {
      errors.mockRestore()
    }
  })

  it('reads the same in English', () => {
    renderLanding('en')
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Check the legal references in your documents against the text in force.',
    )
    expect(screen.getAllByText(STATUS_DATE.en)).toHaveLength(1)
    const main = within(screen.getByRole('main'))
    expect(main.getAllByRole('link', { name: 'Try the demo' })).toHaveLength(2)
    expect(main.getAllByRole('link', { name: 'Write to us for a pilot' })).toHaveLength(2)
  })
})

// ─── The words of the landing block ──────────────────────────────────

type Tree = { [key: string]: string | Tree }

/** Every message of a tree with its path, e.g. "hero.title". */
function leaves(tree: Tree, prefix = ''): Array<[string, string]> {
  return Object.entries(tree).flatMap(([key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key
    return typeof value === 'string' ? [[path, value] as [string, string]] : leaves(value, path)
  })
}

describe.each(LANGUAGES)('landing messages (%s)', (language) => {
  const landing = (MESSAGES[language] as unknown as { landing: Tree }).landing
  // The Codex block is written by another stream and keeps its own typography.
  const own = leaves(landing).filter(([path]) => !path.startsWith('codex.'))

  it('use plain punctuation: no long dashes, ellipsis character or curly quotes', () => {
    for (const [path, text] of own) {
      expect(text, path).not.toMatch(/[\u2013\u2014\u2026\u2018\u2019\u201C\u201D]/)
    }
  })

  it('never put an apostrophe where the message format would read it as an escape', () => {
    // In ICU messages an apostrophe right before a brace, a tag, "#" or "|" starts a quoted run.
    for (const [path, text] of own) expect(text, path).not.toMatch(/'[{}<#|]/)
  })

  it('claim nothing the product cannot show', () => {
    const forbidden =
      /nessun altro|nessuno lo fa|senza allucinazioni|garantit[oaie]\b|real[- ]time|tempo reale|no one else|nobody else|hallucination|guaranteed/i
    for (const [path, text] of own) expect(text, path).not.toMatch(forbidden)
  })

  it('keep one status line and no "in development" labels', () => {
    const status = own.filter(([, text]) => /Stato (al |all')\d|Status on \d/.test(text))
    expect(status.map(([path]) => path)).toEqual(['hero.status'])
    for (const [path, text] of own) expect(text, path).not.toMatch(/in sviluppo|in development|coming soon|prossimamente/i)
  })

  it('describe every act of the corpus', () => {
    const acts = (landing.sources as Tree).acts as Tree
    expect(Object.keys(acts).sort()).toEqual(CORPUS_ACTS.map((act) => act.celex).sort())
  })
})
