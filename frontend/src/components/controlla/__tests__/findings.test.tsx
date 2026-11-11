import { describe, it, expect } from 'vitest'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithIntl } from '@/test/i18n'
import { DEMO_DOCUMENTS } from '@/lib/mock-documents'
import { FindingBody, FindingCard, FindingRow, findingTitle } from '../FindingItem'
import { WordDiff } from '../WordDiff'
import { dependencyOf, type Dependency, type DocumentCheck, type Finding } from '../types'

const doc = (id: string): DocumentCheck => {
  const found = DEMO_DOCUMENTS.find((d) => d.id === id)
  if (!found) throw new Error(`no demo document ${id}`)
  return found
}
const finding = (check: DocumentCheck, code: string): Finding => {
  const found = check.findings.find((f) => f.status.code === code)
  if (!found) throw new Error(`no ${code} in ${check.id}`)
  return found
}
const setting = (check: DocumentCheck) => ({ checkedAt: check.checked_at, lang: check.lang })

const gdpr = doc('demo-doc-gdpr')
const ai = doc('demo-doc-ai')
const csddd = doc('demo-doc-csddd')
const clause = doc('demo-doc-clause')

describe('an altered quote (alterata)', () => {
  const altered = finding(gdpr, 'alterata')

  it('shows where it is, what the document says and the outcome', () => {
    renderWithIntl(<FindingCard finding={altered} {...setting(gdpr)} />)
    const card = screen.getByRole('article', { name: 'GDPR, art. 33, par. 1' })
    expect(within(card).getByText('Citazione diversa dal testo ufficiale')).toBeInTheDocument()
    expect(within(card).getByText('Confrontato con il testo consolidato al 4 maggio 2016')).toBeInTheDocument()
    expect(within(card).getByText('Nel documento, riga 8')).toBeInTheDocument()
    // The reference stands out inside its line of the document.
    expect(within(card).getByText('articolo 33, paragrafo 1, del regolamento (UE) 2016/679').tagName).toBe('STRONG')
    expect(
      within(card).getByText('«senza ingiustificato ritardo e, ove possibile, entro 48 ore dal momento in cui ne è venuto a conoscenza»'),
    ).toBeInTheDocument()
    expect(
      within(card).getByText('La citazione è diversa dal testo vigente: nel documento «48», nel testo ufficiale «72».'),
    ).toBeInTheDocument()
  })

  it('names the words that differ and puts the highlighter on the official ones', () => {
    const { container } = renderWithIntl(<FindingCard finding={altered} {...setting(gdpr)} />)
    const differences = screen.getByText('Parole diverse').parentElement as HTMLElement
    expect(differences).toHaveTextContent('Nel documento «48», nel testo ufficiale «72».')

    const marks = container.querySelectorAll('mark')
    expect(marks).toHaveLength(1)
    expect(marks[0]).toHaveTextContent(/^72$/)
    const quote = marks[0].closest('blockquote') as HTMLElement
    expect(quote).toHaveAttribute('lang', 'it')
    expect(quote).toHaveTextContent('senza ingiustificato ritardo e, ove possibile, entro 72 ore dal momento in cui ne è venuto a conoscenza')

    // The official passage: act, article, the day it was read, the link to EUR-Lex.
    const figure = quote.closest('figure') as HTMLElement
    expect(within(figure).getByText('Regolamento (UE) 2016/679 (GDPR)')).toBeInTheDocument()
    expect(within(figure).getByText(', art. 33, par. 1')).toBeInTheDocument()
    expect(within(figure).getByText('CELEX 32016R0679')).toBeInTheDocument()
    expect(within(figure).getByText('Verificata').parentElement).toHaveAttribute(
      'title',
      'Verificata nel testo ufficiale il 10 novembre 2026',
    )
    expect(within(figure).getByRole('link', { name: /EUR-Lex/ })).toHaveAttribute(
      'href',
      'https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:02016R0679-20160504',
    )
  })

  it('says it in English too, keeping the law in its language', () => {
    renderWithIntl(<FindingCard finding={altered} {...setting(gdpr)} />, { language: 'en' })
    const card = screen.getByRole('article', { name: 'GDPR, art. 33, par. 1' })
    expect(within(card).getByText('Quote differs from the official text')).toBeInTheDocument()
    expect(within(card).getByText('In the document, line 8')).toBeInTheDocument()
    expect(screen.getByText('Words that differ').parentElement).toHaveTextContent('The document has "48", the official text has "72".')
    expect(within(card).getByText('Regulation (EU) 2016/679 (GDPR)')).toBeInTheDocument()
    expect(within(card).getByText('Verified')).toBeInTheDocument()
  })

  it('falls back to the whole official wording when the difference is not one stretch', () => {
    const quote = 'senza ritardo e, ove possibile, entro 48 ore dal giorno in cui ne è venuto a conoscenza'
    const scattered: Finding = {
      ...altered,
      quotes: [quote],
      altered_quote: quote,
      differences: [
        { quoted: '', official: 'ingiustificato' },
        { quoted: '48', official: '72' },
        { quoted: 'giorno', official: 'momento' },
      ],
    }
    const { container } = renderWithIntl(<FindingBody finding={scattered} {...setting(gdpr)} />)
    expect(container.querySelector('mark')).toHaveTextContent(altered.official_quote as string)
    const differences = screen.getByText('Parole diverse').parentElement as HTMLElement
    expect(differences).toHaveTextContent('Nel documento manca «ingiustificato», che nel testo ufficiale c\'è.')
    expect(differences).toHaveTextContent('Nel documento «giorno», nel testo ufficiale «momento».')
  })

  it('tells of a word the document adds', () => {
    const extra: Finding = { ...altered, differences: [{ quoted: 'sempre', official: '' }] }
    renderWithIntl(<FindingBody finding={extra} {...setting(gdpr)} />)
    expect(screen.getByText('Parole diverse').parentElement).toHaveTextContent('Nel documento c\'è «sempre», che nel testo ufficiale non c\'è.')
  })
})

describe('a superseded quote of a changed provision (superata)', () => {
  const outdated = finding(ai, 'superata')

  it('shows the provision before and after, word by word, without relying on colour', () => {
    const { container } = renderWithIntl(<FindingCard finding={outdated} {...setting(ai)} />)
    const card = screen.getByRole('article', { name: 'AI Act, art. 4' })
    expect(within(card).getByText('Citazione superata')).toBeInTheDocument()
    expect(within(card).getByText('Che cosa è cambiato')).toBeInTheDocument()
    expect(within(card).getByText('Dal testo originale al testo consolidato al 27 luglio 2026.')).toBeInTheDocument()

    const removed = Array.from(container.querySelectorAll('p[lang="it"] del'))
    const added = Array.from(container.querySelectorAll('p[lang="it"] ins'))
    expect(removed.map((el) => el.textContent)).toContain(
      'tolto: per garantire nella misura del possibile un livello sufficiente di alfabetizzazione',
    )
    expect(added.map((el) => el.textContent)).toContain("aggiunto: volte a sostenere lo sviluppo dell'alfabetizzazione")
    // Struck through and underlined: the difference is in the line, not only in the tint.
    expect(removed[0].className).toContain('line-through')
    expect(added[0].className).toContain('underline')
    // A screen reader hears which is which; the words are hidden from sight only.
    expect(removed[0].querySelector('.sr-only')).toHaveTextContent('tolto:')
    expect(added[0].querySelector('.sr-only')).toHaveTextContent('aggiunto:')
    expect(within(card).getByText(/c'era prima, oggi non c'è/)).toBeInTheDocument()

    // The new paragraphs are all there as additions.
    const diff = container.querySelector('p[lang="it"]') as HTMLElement
    expect(diff).toHaveTextContent('Tale obbligo non impone ai fornitori o ai deployer di garantire un livello specifico')
    // No official quote for a superseded one: the highlighter stays in the drawer.
    expect(container.querySelector('mark')).toBeNull()
    expect(within(card).getByRole('link', { name: /Testo vigente su EUR-Lex/ })).toHaveAttribute(
      'href',
      'https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:02024R1689-20260727',
    )
  })
})

describe('WordDiff', () => {
  it('shortens long unchanged stretches and says so', () => {
    const filler = Array.from({ length: 80 }, (_, i) => `parola${i}`).join(' ')
    renderWithIntl(<WordDiff before={`${filler} entro 48 ore`} after={`${filler} entro 72 ore`} />)
    expect(screen.getByText('[...]')).toBeInTheDocument()
    expect(screen.getByText('51 parole uguali omesse')).toBeInTheDocument()
    expect(screen.getByText('48', { selector: 'del' })).toBeInTheDocument()
    expect(screen.getByText('72', { selector: 'ins' })).toBeInTheDocument()
  })

  it('says when the two versions are the same', () => {
    renderWithIntl(<WordDiff before="Articolo 5 Pratiche vietate" after={'Articolo 5\nPratiche vietate'} />)
    expect(screen.getByText('Il testo è uguale nelle due versioni.')).toBeInTheDocument()
  })
})

describe('the other outcomes', () => {
  it('verified quote (verificata): the official wording under the highlighter, verified on the day of the check', () => {
    const verified = finding(gdpr, 'verificata')
    const { container } = renderWithIntl(<FindingBody finding={verified} {...setting(gdpr)} />)
    expect(container.querySelectorAll('mark')).toHaveLength(1)
    expect(container.querySelector('mark')).toHaveTextContent(
      "il titolare del trattamento comunica la violazione all'interessato senza ingiustificato ritardo",
    )
    expect(screen.getByText('Verificata')).toBeInTheDocument()
    expect(screen.getByText('La citazione è nel testo vigente, parola per parola.')).toBeInTheDocument()
    expect(screen.queryByText('Parole diverse')).not.toBeInTheDocument()
  })

  it('quote in another article (altro_articolo): the passage without the article the document names', () => {
    const elsewhere = finding(gdpr, 'altro_articolo')
    const { container } = renderWithIntl(<FindingCard finding={elsewhere} {...setting(gdpr)} />)
    expect(screen.getByText('Citazione in un altro articolo')).toBeInTheDocument()
    expect(screen.getByText('La citazione è nel testo vigente, ma in Art. 33, non nella disposizione citata.')).toBeInTheDocument()
    const figure = container.querySelector('figure.border-mark-deep') as HTMLElement
    expect(within(figure).getByText('Regolamento (UE) 2016/679 (GDPR)')).toBeInTheDocument()
    expect(within(figure).queryByText(/art\. 28/)).not.toBeInTheDocument()
  })

  it('provision that does not exist (inesistente): the reason and the way to the text in force', () => {
    const missing = finding(gdpr, 'inesistente')
    const { container } = renderWithIntl(<FindingCard finding={missing} {...setting(gdpr)} />)
    expect(screen.getByRole('article', { name: 'GDPR, art. 33, par. 6' })).toBeInTheDocument()
    expect(screen.getByText('Non esiste nel testo vigente')).toBeInTheDocument()
    expect(
      screen.getByText("Il paragrafo 6 non esiste nel testo consolidato al 04/05/2016: l'art. 33 ha i paragrafi da 1 a 5."),
    ).toBeInTheDocument()
    expect(container.querySelector('mark')).toBeNull()
    expect(screen.getByRole('link', { name: /Testo vigente su EUR-Lex/ })).toBeInTheDocument()
  })

  it('provision gone from the text in force, with how it read before', () => {
    const repealed: Finding = {
      ...finding(gdpr, 'inesistente'),
      before: { version_label: 'testo consolidato al 17/04/2025', text: 'Articolo 22\nTesto di allora.' },
      after_text: null,
    }
    renderWithIntl(<FindingBody finding={repealed} {...setting(gdpr)} />)
    expect(screen.getByText("Com'era nel testo consolidato al 17 aprile 2025")).toBeInTheDocument()
    expect(screen.getByText(/Testo di allora\./)).toBeInTheDocument()
    expect(screen.queryByText('Che cosa è cambiato')).not.toBeInTheDocument()
  })

  it('valid reference and uncovered law (valido, non_coperto) are one line that opens', async () => {
    const user = userEvent.setup()
    const uncovered = finding(gdpr, 'non_coperto')
    renderWithIntl(
      <>
        <FindingRow finding={finding(gdpr, 'valido')} {...setting(gdpr)} />
        <FindingRow finding={uncovered} {...setting(gdpr)} />
      </>,
    )
    expect(screen.getByText('Riferimento valido')).toBeInTheDocument()
    expect(screen.getByText('Non coperto da NormaAI')).toBeInTheDocument()
    const row = screen.getByText('D.Lgs. 196/2003 (Codice privacy), art. 154').closest('details') as HTMLDetailsElement
    expect(row.open).toBe(false)
    await user.click(screen.getByText('D.Lgs. 196/2003 (Codice privacy), art. 154'))
    expect(row.open).toBe(true)
    expect(within(row).getByText('riga 29')).toBeInTheDocument()
    expect(within(row).getByRole('link', { name: /Apri su Normattiva/ })).toHaveAttribute(
      'href',
      'https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2003;196',
    )
  })

  it('an outcome the interface does not know keeps the words of the server', () => {
    const unknown: Finding = { ...finding(gdpr, 'valido'), status: { code: 'rinumerato', label: 'Articolo rinumerato' } }
    renderWithIntl(<FindingCard finding={unknown} {...setting(gdpr)} />)
    expect(screen.getByText('Articolo rinumerato')).toBeInTheDocument()
  })

  it('a reference without an act says so, and a link that is not a web address is not offered', () => {
    const bare: Finding = {
      ...finding(gdpr, 'valido'),
      act: null,
      provision: { key: 'art:22', label: 'art. 22' },
      status: { code: 'atto_mancante', label: 'Atto non indicato' },
      url: 'javascript:alert(1)',
    }
    expect(findingTitle(bare, 'Atto non indicato')).toBe('Atto non indicato, art. 22')
    renderWithIntl(<FindingCard finding={bare} {...setting(gdpr)} />)
    expect(screen.getByRole('article', { name: 'Atto non indicato, art. 22' })).toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })

  it('an English document keeps its law in English', () => {
    const verified = finding(clause, 'verificata')
    const { container } = renderWithIntl(<FindingBody finding={verified} {...setting(clause)} />, { language: 'en' })
    expect(container.querySelector('blockquote[lang="en"] mark')).toHaveTextContent(
      'processes the personal data only on documented instructions from the controller',
    )
    expect(screen.getByRole('link', { name: /EUR-Lex/ })).toHaveAttribute('href', expect.stringContaining('/legal-content/EN/TXT/'))
  })
})

describe('a finding whose provision changed after the check', () => {
  // The re-check found article 2 of the CSDDD changed: the server moved the finding
  // under "correggere" with the article then and now, and kept what the check had read.
  const changed = csddd.findings.find((f) => f.provision?.key === 'art:2') as Finding
  const dependency = dependencyOf(csddd, changed) as Dependency

  it('is matched to its dependency through the link the server gives', () => {
    expect(changed.dependency).toEqual({ source: 'eurlex', act: '32024L1760', key: 'art:2' })
    expect(dependency).toMatchObject({ article: 'Art. 2', state: 'changed', current_as_of: '2026-03-18' })
    // Without the link, the act and the provision still find it.
    expect(dependencyOf(csddd, { ...changed, dependency: undefined })).toBe(dependency)
    expect(dependencyOf(csddd, { ...changed, dependency: { source: 'eurlex', act: '32024L1760', key: 'art:99' } })).toBeUndefined()
  })

  it('says first that the provision changed, and which text the outcome was for', () => {
    renderWithIntl(<FindingCard finding={changed} dependency={dependency} {...setting(csddd)} />)
    const card = screen.getByRole('article', { name: 'CSDDD, art. 2, par. 1' })
    // The words of the re-check, not those of a change after the document's date.
    expect(within(card).getByText('Cambiato dopo il controllo')).toBeInTheDocument()
    expect(within(card).queryByText('Cambiato dopo la data del documento')).not.toBeInTheDocument()
    expect(within(card).queryByText('Norma cambiata dopo il controllo')).not.toBeInTheDocument()
    expect(
      within(card).getByText(
        "Dopo il controllo questa norma è cambiata: oggi vale il testo consolidato al 18 marzo 2026. L'esito e la citazione qui sotto sono quelli del controllo, sul testo consolidato al 17 aprile 2025.",
      ),
    ).toBeInTheDocument()
    expect(within(card).getByText('Confrontato con il testo consolidato al 18 marzo 2026')).toBeInTheDocument()

    // What the check found on that day stays, under its own name; the sentence of the re-check is not repeated.
    const outcome = within(card).getByText('Esito al momento del controllo').parentElement as HTMLElement
    expect(within(outcome).getAllByRole('listitem').map((li) => li.textContent)).toEqual([
      'Art. 2, par. 1 esiste nel testo consolidato al 17/04/2025.',
      'La citazione è nel testo vigente, parola per parola.',
    ])
  })

  it('no longer shows the wording of that day as the law in force', () => {
    const { container } = renderWithIntl(<FindingCard finding={changed} dependency={dependency} {...setting(csddd)} />)
    expect(screen.queryByText('Verificata')).not.toBeInTheDocument()
    expect(screen.queryByText('Il testo ufficiale dice')).not.toBeInTheDocument()
    const then = screen.getByText('Al controllo il testo ufficiale diceva (testo consolidato al 17 aprile 2025)').parentElement as HTMLElement
    expect(then).toHaveTextContent('in media, più di 1 000 dipendenti e un fatturato netto a livello mondiale superiore a 450 000 000 EUR')
    // No highlighter anywhere: nothing shown here is a passage of the law in force quoted by the document.
    expect(container.querySelector('mark')).toBeNull()
  })

  it('shows what changed between the text of the check and the text in force', () => {
    const { container } = renderWithIntl(<FindingCard finding={changed} dependency={dependency} {...setting(csddd)} />)
    expect(screen.getByText('Dal testo consolidato al 17 aprile 2025 al testo consolidato al 18 marzo 2026.')).toBeInTheDocument()
    const removed = Array.from(container.querySelectorAll('p[lang="it"] del')).map((el) => el.textContent)
    const added = Array.from(container.querySelectorAll('p[lang="it"] ins')).map((el) => el.textContent)
    // The thresholds, each as one number replaced by another.
    expect(removed).toContain('tolto: 1 000')
    expect(added).toContain('aggiunto: 5 000')
    expect(removed).toContain('tolto: 450 000 000')
    expect(added).toContain('aggiunto: 1 500 000 000')
    expect(screen.getByRole('link', { name: /Testo vigente su EUR-Lex/ })).toHaveAttribute(
      'href',
      'https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:02024L1760-20260318',
    )
  })

  it('says it in English', () => {
    renderWithIntl(<FindingCard finding={changed} dependency={dependency} {...setting(csddd)} />, { language: 'en' })
    expect(screen.getByText('Changed after the check')).toBeInTheDocument()
    expect(
      screen.getByText(
        'After the check this provision changed: today the consolidated text of 18 March 2026 applies. The outcome and the quote below are those of the check, on the consolidated text of 17 April 2025.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByText('From the consolidated text of 17 April 2025 to the consolidated text of 18 March 2026.')).toBeInTheDocument()
  })

  // What follows does not depend on the server rewriting the finding: only the
  // state of the provision says it changed (the shape of the agreed contract).
  const verified = finding(gdpr, 'verificata')
  const stale = (state: 'changed' | 'removed'): Dependency => ({
    ...(dependencyOf(gdpr, verified) as Dependency),
    state,
    changed_at: '2026-11-11T05:00:00Z',
    current_version: null,
    current_as_of: null,
    message: null,
  })

  it('warns on a finding the server left as it was', async () => {
    const user = userEvent.setup()
    const { container } = renderWithIntl(<FindingRow finding={verified} dependency={stale('changed')} {...setting(gdpr)} />)
    // The line that stays closed carries the warning next to the outcome of the day.
    expect(screen.getByText('Citazione verificata')).toBeInTheDocument()
    expect(screen.getByText('Norma cambiata dopo il controllo')).toBeInTheDocument()
    await user.click(screen.getByText('GDPR, art. 34, par. 1'))
    expect(
      screen.getByText(
        "Dopo il controllo questa norma è cambiata. L'esito e la citazione qui sotto sono quelli del controllo, sul testo consolidato al 4 maggio 2016.",
      ),
    ).toBeInTheDocument()
    expect(screen.queryByText('Verificata')).not.toBeInTheDocument()
    expect(container.querySelector('mark')).toBeNull()
    expect(screen.getByText('Al controllo il testo ufficiale diceva (testo consolidato al 4 maggio 2016)')).toBeInTheDocument()
  })

  it('says when the provision is no longer in the text in force', () => {
    renderWithIntl(<FindingBody finding={verified} dependency={stale('removed')} {...setting(gdpr)} />)
    expect(
      screen.getByText(
        "Dopo il controllo questa norma è uscita dal testo vigente. L'esito e la citazione qui sotto sono quelli del controllo, sul testo consolidato al 4 maggio 2016.",
      ),
    ).toBeInTheDocument()
  })

  it('keeps an altered quote readable, without calling the old wording verified', () => {
    const altered = finding(gdpr, 'alterata')
    const { container } = renderWithIntl(<FindingCard finding={altered} dependency={stale('changed')} {...setting(gdpr)} />)
    expect(screen.getByText('Citazione diversa dal testo ufficiale')).toBeInTheDocument()
    expect(screen.getByText('Norma cambiata dopo il controllo')).toBeInTheDocument()
    expect(screen.getByText('Parole diverse').parentElement).toHaveTextContent('Nel documento «48», nel testo ufficiale «72».')
    expect(container.querySelector('mark')).toBeNull()
    expect(screen.queryByText('Verificata')).not.toBeInTheDocument()
  })

  it('stays verified when the provision did not change', () => {
    const unchanged = csddd.findings.find((f) => f.provision?.key === 'art:14') as Finding
    expect(dependencyOf(csddd, unchanged)?.state).toBe('current')
    renderWithIntl(<FindingBody finding={verified} dependency={dependencyOf(gdpr, verified)} {...setting(gdpr)} />)
    expect(screen.getByText('Verificata')).toBeInTheDocument()
    expect(screen.queryByText(/Dopo il controllo questa norma/)).not.toBeInTheDocument()
    expect(screen.queryByText('Norma cambiata dopo il controllo')).not.toBeInTheDocument()
  })
})
