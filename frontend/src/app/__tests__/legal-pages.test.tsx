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
    expect(main).toHaveTextContent('Google LLC (API Gemini, USA)')
    expect(main).not.toHaveTextContent(/scade dopo 30 giorni|EUR-Lex e Normattiva/)
    expect(main).toHaveTextContent('Ultimo aggiornamento: 11 novembre 2026')
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
    expect(main).not.toHaveTextContent(/lavoro in corso|In lavorazione/)
    // every step and every documented choice points at the code behind it
    expect(within(main).getAllByText('Nel codice:', { exact: false }).length).toBeGreaterThanOrEqual(6 + 5)
  })
})
