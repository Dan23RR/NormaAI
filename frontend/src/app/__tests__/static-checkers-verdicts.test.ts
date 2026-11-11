import { beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

/**
 * The two static checkers decide in the browser, with a script inside the
 * page. This suite loads each page into the test DOM, runs that same script
 * and walks every verdict, so the rule logic cannot change unnoticed. The
 * lead form is never submitted: `fetch` is a spy that must stay silent.
 */

const PUBLIC = join(__dirname, '..', '..', '..', 'public')

function mount(name: string): void {
  const html = readFileSync(join(PUBLIC, name), 'utf8')
  const body = html.slice(html.indexOf('<body>') + '<body>'.length, html.indexOf('</body>'))
  const scripts = [...body.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1])
  expect(scripts).toHaveLength(1)
  document.body.innerHTML = body.replace(/<script>[\s\S]*?<\/script>/g, '')
  new Function(scripts[0])()
}

const $ = <T extends HTMLElement = HTMLElement>(selector: string) => document.querySelector(selector) as T
const all = (selector: string) => Array.from(document.querySelectorAll<HTMLElement>(selector))
const badge = () => $('#result .badge')?.textContent?.trim()
const resultText = () => $('#result').textContent ?? ''
const submit = () => $<HTMLFormElement>('#calc').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))

function tick(id: string, checked = true): void {
  const box = $<HTMLInputElement>(`#${id}`)
  box.checked = checked
  box.dispatchEvent(new Event('change', { bubbles: true }))
}

let fetchSpy: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchSpy = vi.fn()
  vi.stubGlobal('fetch', fetchSpy)
  Element.prototype.scrollIntoView = vi.fn()
})

describe('AI Act checker verdicts', () => {
  beforeEach(() => mount('scope-aiact.html'))

  it('gives no verdict on a form nobody touched', () => {
    submit()
    expect(badge()).toBe('Nessuna risposta')
    expect($('#lead')).toBeNull()
  })

  it('says "outside article 50" only after an explicit answer', () => {
    $('.chip[data-set=""]').click()
    expect(badge()).toBe("Nessun obbligo dell'articolo 50 individuato")
    expect(all('#result .ob')).toHaveLength(0)
    expect(all('#result ul.notes li')).toHaveLength(4)
    expect(resultText()).toContain('2 dicembre 2027')
    expect(resultText()).toContain('2 agosto 2028')
  })

  it.each([
    ['chat', 1, 'art. 50, par. 1', 'Obbligo del fornitore'],
    ['gen', 2, 'art. 50, par. 2', 'Obbligo del fornitore'],
    ['emo', 1, 'art. 50, par. 3', 'Obbligo del deployer'],
    ['deep', 2, 'art. 50, par. 4', 'Obbligo del deployer'],
  ])('shows the obligation and its passage of law for "%s"', (key, quotes, reference, who) => {
    tick(`q-${key}`)
    expect($(`#q-${key}`).closest('label')?.className).toBe('chk on')
    submit()
    expect(badge()).toBe('Obblighi applicabili dal 2 agosto 2026')
    expect(all('#result .ob')).toHaveLength(1)
    expect(all('#result figure.law mark')).toHaveLength(quotes)
    expect($('#result .ob .badge').textContent).toBe(who)
    expect($('#result figure.law figcaption').textContent).toContain(reference)
    expect($('#result figure.law a').getAttribute('href')).toBe(
      'https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:02024R1689-20260727',
    )
  })

  it('names 2 December 2026 for generative systems already on the market', () => {
    tick('q-gen')
    submit()
    expect(resultText()).toContain('entro il 2 dicembre 2026')
    expect(resultText()).toContain('art. 111, par. 4')
  })

  it('lists the four obligations together, with sanctions, the Italian authorities and what is not applicable yet', () => {
    for (const key of ['chat', 'gen', 'emo', 'deep']) tick(`q-${key}`)
    submit()
    expect(all('#result .ob')).toHaveLength(4)
    expect(all('#result figure.law')).toHaveLength(6)
    expect(resultText()).toContain('15 milioni di euro')
    expect(resultText()).toContain('legge 23 settembre 2025, n. 132')
    expect($('#result .later').textContent).toContain('regolamento (UE) 2026/1744')
  })

  it('follows the examples, and an emptied form after an answer is an answer', () => {
    $('.chip[data-set="chat"]').click()
    expect(all('#result .ob')).toHaveLength(1)
    $('.chip[data-set="chat,gen"]').click()
    expect(all('#result .ob')).toHaveLength(2)
    tick('q-chat', false)
    tick('q-gen', false)
    submit()
    expect(badge()).toBe("Nessun obbligo dell'articolo 50 individuato")
  })

  it('offers the lead form with a real verdict and sends nothing by itself', () => {
    $('.chip[data-set="chat,gen"]').click()
    expect($('#lead #org')).not.toBeNull()
    expect($<HTMLInputElement>('#lead #email').type).toBe('email')
    expect($<HTMLInputElement>('#lead #contact_time').name).toBe('contact_time')
    expect(resultText()).toContain('30 minuti')
    expect(fetchSpy).not.toHaveBeenCalled()
  })
})

describe('CSRD checker verdicts', () => {
  beforeEach(() => mount('scope-csrd.html'))

  function check(employees: string, revenue: string, opts: { listed?: boolean; wave1?: boolean } = {}): void {
    $<HTMLInputElement>('#emp').value = employees
    $<HTMLInputElement>('#rev').value = revenue
    $<HTMLInputElement>('#listed').checked = Boolean(opts.listed)
    $<HTMLInputElement>('#wave1').checked = Boolean(opts.wave1)
    submit()
  }

  it('asks for the two numbers when they are missing or not numbers', () => {
    submit()
    expect(badge()).toBe('Dati mancanti')
    check('abc', '10')
    expect(badge()).toBe('Dati mancanti')
    expect($('#lead')).toBeNull()
  })

  // The classification as it has always been: both thresholds must be EXCEEDED
  // (more than 1,000 employees and more than EUR 450 million), one alone or a
  // value close to a threshold is the borderline band, a listed company below
  // both is borderline too.
  it.each([
    ['600', '120', 'Fuori ambito'],
    ['100', '10', 'Fuori ambito'],
    ['849', '379', 'Fuori ambito'],
    ['1500', '620', 'In ambito'],
    ['1001', '450,1', 'In ambito'],
    ['1000', '450', 'Fuori ambito oggi, vicino al confine'],
    ['1001', '450', 'Fuori ambito oggi, vicino al confine'],
    ['1200', '380', 'Fuori ambito oggi, vicino al confine'],
    ['900', '500', 'Fuori ambito oggi, vicino al confine'],
    ['850', '100', 'Fuori ambito oggi, vicino al confine'],
    ['100', '380', 'Fuori ambito oggi, vicino al confine'],
    ['3000', '100', 'Fuori ambito oggi, vicino al confine'],
  ])('%s employees and %s million: %s', (employees, revenue, expected) => {
    check(employees, revenue)
    expect(badge()).toBe(expected)
  })

  it('treats a listed company below both thresholds as borderline, and says why', () => {
    check('100', '10', { listed: true })
    expect(badge()).toBe('Fuori ambito oggi, vicino al confine')
    expect($('#result .v-body').textContent).toContain('piccole e medie imprese quotate')
  })

  it('explains which threshold is exceeded', () => {
    check('1200', '380')
    expect($('#result .v-body').textContent).toContain('soglia dei dipendenti ma non quella dei ricavi')
    expect(resultText()).not.toContain('Richieste dei clienti')
    check('900', '500')
    expect($('#result .v-body').textContent).toContain('soglia dei ricavi ma non quella dei dipendenti')
    expect(resultText()).toContain('Richieste dei clienti')
    check('900', '100')
    expect($('#result .v-body').textContent).toContain('a ridosso di una soglia')
  })

  it('reads Italian number formats and shows them grouped', () => {
    check('1.200', '380,5')
    const values = all('#result .axis .val').map((el) => el.textContent?.trim())
    expect(values[0]).toMatch(/^1[.,]200$/)
    expect(values[1]).toMatch(/^380[.,]5 milioni di euro$/)
  })

  it('adds the due diligence note only above its own thresholds', () => {
    check('6000', '2000')
    expect(badge()).toBe('In ambito')
    expect(resultText()).toContain('Attenzione alla CSDDD')
    check('5000', '2000')
    expect(resultText()).not.toContain('Attenzione alla CSDDD')
  })

  it('quotes the directive and dates what it says', () => {
    check('1500', '620')
    expect($('#result figure.law mark').textContent).toContain('superiori a 450')
    expect($('#result figure.law figcaption').textContent).toContain('art. 19 bis, par. 1')
    expect(resultText()).toContain('1° gennaio 2027')
    check('600', '120')
    expect(resultText()).toContain('art. 17, comma 3-bis')
    expect(resultText()).toContain('26 luglio 2029')
    expect($('#asof-line').textContent).toContain("Aggiornato all'11 novembre 2026")
  })

  it('has a note for those who already report, different in and out of scope', () => {
    check('1500', '620', { wave1: true })
    expect(resultText()).toContain('Continui senza interruzione')
    check('1200', '380', { wave1: true })
    expect(resultText()).toContain('possibilità di esentare')
    check('600', '120', { wave1: true })
    expect(all('#result ul.notes li')).toHaveLength(4)
  })

  it('follows the three examples and sends nothing by itself', () => {
    $('.chip[data-e="600"]').click()
    expect(badge()).toBe('Fuori ambito')
    $('.chip[data-e="1200"]').click()
    expect(badge()).toBe('Fuori ambito oggi, vicino al confine')
    $('.chip[data-e="1500"]').click()
    expect(badge()).toBe('In ambito')
    expect($<HTMLInputElement>('#lead #contact_time').name).toBe('contact_time')
    expect(resultText()).toContain('30 minuti')
    expect(fetchSpy).not.toHaveBeenCalled()
  })
})
