import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import type { ReactElement } from 'react'
import { IntlWrapper } from '@/test/i18n'
import { renderServerPage, setServerLanguage } from '@/test/server-page'
import type { Language } from '@/i18n/config'
import PrivacyPage from '../privacy/page'
import TermsPage from '../terms/page'
import CookiePage from '../cookie/page'
import SecurityPage from '../security/page'
import MetodoPage from '../metodo/page'
import { COOKIES, LOCAL_STORAGE, SESSION_STORAGE } from '../cookie/storage-keys'

vi.mock('next-intl/server', () => import('@/test/server-page').then((m) => m.nextIntlServerMock))

vi.mock('next/link', () => ({
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  default: ({ children, href, ...props }: any) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}))

// The header only asks whether a session exists.
vi.mock('@/lib/auth', () => ({ getAccessToken: () => null }))

async function show(page: ReactElement, language: Language = 'it') {
  setServerLanguage(language)
  return render(<IntlWrapper language={language}>{await renderServerPage(page)}</IntlWrapper>)
}

const PAGES: Array<{ name: string; page: () => ReactElement; it: string; en: string }> = [
  { name: 'privacy', page: () => <PrivacyPage />, it: 'Privacy Policy', en: 'Privacy Policy' },
  { name: 'terms', page: () => <TermsPage />, it: 'Termini di Servizio', en: 'Terms of Service' },
  { name: 'cookie', page: () => <CookiePage />, it: 'Cookie Policy', en: 'Cookie Policy' },
  { name: 'security', page: () => <SecurityPage />, it: 'Sicurezza', en: 'Security' },
  { name: 'metodo', page: () => <MetodoPage />, it: 'Come nasce una risposta, e quando non arriva.', en: 'How an answer is made, and when it does not come.' },
]

describe('legal and method pages', () => {
  afterEach(() => {
    cleanup()
    setServerLanguage('it')
  })

  // A missing key or argument throws in the test doubles, so rendering is the check.
  it.each(PAGES)('$name renders whole in Italian and in English', async ({ page, it: italian, en: english }) => {
    await show(page(), 'it')
    expect(screen.getByRole('heading', { level: 1, name: italian })).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/\b(legal|site|login|ui)\.[a-zA-Z]+\.[a-zA-Z.]+/)
    cleanup()
    await show(page(), 'en')
    expect(screen.getByRole('heading', { level: 1, name: english })).toBeInTheDocument()
  })

  it('security: says what is true of the code today', async () => {
    await show(<SecurityPage />)
    const main = screen.getByRole('main')
    // one dated status line while no backend is configured, and no promise of days
    expect(main).toHaveTextContent('Gli account sono sospesi mentre il server dell’applicazione viene spostato.')
    expect(main).toHaveTextContent('Ultimo aggiornamento di questo stato: 11 novembre 2026.')
    expect(main).not.toHaveTextContent(/qualche giorno|girano su un server Hetzner/)
    // row level security is on the tenant data tables, not on users
    expect(main).toHaveTextContent('Le tabelle degli utenti e delle organizzazioni non hanno queste policy, per scelta')
    expect(main).not.toHaveTextContent('Row Level Security su utenti')
    // the Codex link is a public file, releases do not exist yet, the model is a configured provider
    expect(main).toHaveTextContent('non è firmato e non scade')
    expect(main).toHaveTextContent('Non esiste ancora una release pubblicata.')
    expect(main).not.toHaveTextContent('Gemini 2.5')
    expect(main).toHaveTextContent('La configurazione misurata, e prevista per il server, è anthropic: Claude di Anthropic')
    expect(main).not.toHaveTextContent('Oggi il valore predefinito è gemini')
    expect(main).toHaveTextContent('Il controllo dei documenti non manda nulla a un modello linguistico.')
    expect(main).toHaveTextContent('solo con il nonce della richiesta, diverso a ogni richiesta')
    expect(main).toHaveTextContent('niente unsafe-inline né unsafe-eval per gli script')
    expect(main).toHaveTextContent('con tutte le capability Linux tolte salvo NET_BIND_SERVICE')
    // the lead route writes to nobody but the operator, and limits each address
    expect(main).toHaveTextContent('che non scrive mai all’indirizzo inserito nel modulo')
    expect(main).toHaveTextContent('al massimo 10 richieste l’ora da uno stesso indirizzo IP')
    expect(main).toHaveTextContent('Il token di accesso dura 60 minuti')
    // what a document check keeps
    expect(main).toHaveTextContent('il file viene elaborato in memoria e non viene conservato')
    expect(main).toHaveTextContent('al massimo 160 caratteri di contesto')
  })

  it('privacy: names where the data goes and what a document check keeps', async () => {
    await show(<PrivacyPage />)
    const main = screen.getByRole('main')
    expect(main).toHaveTextContent('Documenti controllati: il file che carichi per controllarne i riferimenti di legge viene elaborato in memoria e non viene conservato.')
    expect(main).toHaveTextContent('la domanda e i passaggi recuperati vanno invece al fornitore del modello linguistico')
    // the provider of the measured configuration receives the questions; the others are options
    expect(main).toHaveTextContent('Anthropic PBC (USA): Claude, il modello linguistico che scrive le risposte')
    expect(main).toHaveTextContent('il codice permette in alternativa Google (API Gemini, USA), Mistral AI')
    expect(main).not.toHaveTextContent(/predefinit[oa]\W+Google|Google Gemini\) per scrivere/)
    // commercial follow-up rests on an unticked box, not on legitimate interest
    expect(main).toHaveTextContent('solo con il tuo consenso, dato spuntando nel modulo la casella che parte vuota')
    expect(main).toHaveTextContent('art. 130 del Codice privacy')
    expect(main).not.toHaveTextContent('Invio del Codex e ricontatto sullo stesso tema a chi lo ha richiesto: legittimo interesse')
    expect(main).toHaveTextContent('Senza consenso, per il Codex non è registrato nulla che ti identifichi')
    expect(main).not.toHaveTextContent(/scade dopo 30 giorni|EUR-Lex e Normattiva/)
    expect(main).toHaveTextContent('Ultimo aggiornamento: 18 novembre 2026')
  })

  it('terms: carries the imprint, with no VAT line when none is configured', async () => {
    await show(<TermsPage />)
    const main = screen.getByRole('main')
    expect(within(main).getByRole('heading', { name: 'Chi gestisce NormaAI' })).toBeInTheDocument()
    expect(main).toHaveTextContent(
      'NormaAI è un progetto di Daniel Culotta, persona fisica, Inverigo (CO), Italia, non ancora costituito in società.',
    )
    expect(main).not.toHaveTextContent('Partita IVA')
    expect(main).toHaveTextContent('le verifiche di ambito applicano regole scritte a mano ai dati che inserisci')
  })

  it('terms: limit liability within the law and say price, duration, law and court', async () => {
    await show(<TermsPage />)
    const main = screen.getByRole('main')
    const text = main.textContent ?? ''
    // A blanket exclusion is void for wilful misconduct and gross negligence (art. 1229 c.c.),
    // and a cap equal to the fees of a free service excludes everything.
    expect(text).not.toMatch(/in alcun caso|corrispettivi pagati/)
    expect(main).toHaveTextContent('Il gestore risponde dei danni causati con dolo o colpa grave: questa responsabilità non è esclusa né limitata.')
    expect(main).toHaveTextContent('né i diritti che ti riconosce il Codice del consumo')
    // who, price, duration and withdrawal
    expect(main).toHaveTextContent('Il servizio è offerto dalla persona indicata qui sopra')
    expect(main).toHaveTextContent('pilot gratuito e su invito')
    expect(main).toHaveTextContent('non è richiesto né incassato alcun pagamento')
    expect(main).toHaveTextContent('Puoi recedere in qualsiasi momento, senza costi')
    // law and court
    expect(main).toHaveTextContent('Questi termini sono regolati dalla legge italiana.')
    expect(main).toHaveTextContent('art. 66-bis del Codice del consumo')
    // the model provider of the measured configuration, and no AI claimed for the document check
    expect(main).toHaveTextContent('Claude di Anthropic')
    expect(main).not.toHaveTextContent('Gemini')
    expect(main).toHaveTextContent('il controllo dei documenti e i suoi avvisi confrontano le parole con il testo ufficiale senza modelli generativi')
    const sections = within(main)
      .getAllByRole('heading', { level: 2 })
      .map((h) => h.textContent)
    expect(sections.map((title) => Number.parseInt(title ?? '', 10))).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
  })

  it('terms: say the same in English', async () => {
    await show(<TermsPage />, 'en')
    const main = screen.getByRole('main')
    expect(main.textContent).not.toMatch(/in no case|fees paid/)
    expect(main).toHaveTextContent('The operator is liable for damage caused by wilful misconduct or gross negligence')
    expect(main).toHaveTextContent('free, invitation-only pilot')
    expect(main).toHaveTextContent('These terms are governed by Italian law.')
    expect(main).toHaveTextContent('Art. 66-bis of the Italian Consumer Code')
  })

  it('cookie: lists exactly the keys of storage-keys.ts', async () => {
    await show(<CookiePage />)
    const cells = screen.getAllByRole('cell').map((cell) => cell.textContent)
    for (const row of [...COOKIES, ...LOCAL_STORAGE, ...SESSION_STORAGE]) expect(cells).toContain(row.key)
    expect(screen.getAllByRole('row')).toHaveLength(COOKIES.length + LOCAL_STORAGE.length + SESSION_STORAGE.length + 3)
    expect(cells).not.toContain('normaai-workflow-items')
  })

  it('method: the pipeline in the order the code runs it, with what is off said to be off', async () => {
    await show(<MetodoPage />)
    const steps = screen
      .getAllByRole('heading', { level: 3 })
      .map((h) => h.textContent)
      .slice(0, 6)
    expect(steps).toEqual([
      'Recupero ibrido',
      'Redazione dal testo recuperato',
      'Controllo di aderenza alle fonti',
      'Verifica letterale delle citazioni',
      'Campionamento multiplo, spento per impostazione predefinita',
      'Chain-of-Verification, su richiesta',
    ])
    const main = screen.getByRole('main')
    expect(main).toHaveTextContent('i controlli sempre attivi sono l’aderenza alle fonti e la verifica letterale delle citazioni')
    expect(main).toHaveTextContent('Da novembre 2026 una citazione conta come verificata solo se è letterale')
    expect(main).toHaveTextContent('Il corpus delle risposte contiene 18 atti dell’Unione')
    expect(main).toHaveTextContent('Oggi il corpus non contiene leggi nazionali italiane.')
    expect(main).toHaveTextContent('nella configurazione misurata, Claude di Anthropic')
    expect(main).not.toHaveTextContent('Google Gemini')
    expect(main).not.toHaveTextContent(/lavoro in corso|In lavorazione/)
    // every step and every documented choice points at the code behind it
    expect(within(main).getAllByText('Nel codice:', { exact: false }).length).toBeGreaterThanOrEqual(6 + 5)
  })
})
