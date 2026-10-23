import { describe, it, expect } from 'vitest'
import { assessScope, classifyCsrd, aiObligations, SCOPE_DATES } from '../rules'
import { EMPTY_INPUT, NO_AI, keysToAi } from '../query'
import { VERIFIED_ON } from '../sources'
import type { ScopeInput, ScopeResult } from '../types'
import { textContextFor } from '@/test/i18n'

const M = 1_000_000
const it_ = textContextFor('it')
const en = textContextFor('en')

function company(partial: Partial<ScopeInput>): ScopeInput {
  return { ...EMPTY_INPUT, ...partial }
}

function result(input: ScopeInput, framework: ScopeResult['framework'], ctx = it_): ScopeResult {
  const r = assessScope(input, ctx).results.find((x) => x.framework === framework)
  if (!r) throw new Error(`no result for ${framework}`)
  return r
}

describe('classifyCsrd (port of public/scope-csrd.html)', () => {
  it('600 dipendenti e 120 M€: fuori (esempio del Codex, Studio Fashion)', () => {
    expect(classifyCsrd(600, 120 * M, false)).toBe('out')
  })
  it('1.200 dipendenti e 380 M€: una sola soglia superata, sul filo (esempio del Codex, Manufacturing Co.)', () => {
    expect(classifyCsrd(1200, 380 * M, false)).toBe('filo')
  })
  it('1.500 dipendenti e 620 M€: in ambito (esempio del Codex, Industrial Group)', () => {
    expect(classifyCsrd(1500, 620 * M, false)).toBe('in')
  })
  it('esattamente 1.000 e 450 M€: le soglie sono strette (più di), quindi non superate ma a ridosso', () => {
    expect(classifyCsrd(1000, 450 * M, false)).toBe('filo')
  })
  it('1.001 dipendenti e 450,1 M€: appena sopra entrambe, in ambito', () => {
    expect(classifyCsrd(1001, 450.1 * M, false)).toBe('in')
  })
  it('900 dipendenti e 100 M€: fascia 850-1.200 dipendenti, sul filo', () => {
    expect(classifyCsrd(900, 100 * M, false)).toBe('filo')
  })
  it('300 dipendenti e 400 M€: fascia 380-550 M€, sul filo', () => {
    expect(classifyCsrd(300, 400 * M, false)).toBe('filo')
  })
  it('500 dipendenti e 100 M€ quotata: caso di confine', () => {
    expect(classifyCsrd(500, 100 * M, true)).toBe('filo')
  })
  it('500 dipendenti e 100 M€ non quotata: fuori', () => {
    expect(classifyCsrd(500, 100 * M, false)).toBe('out')
  })
  it('solo ricavi oltre soglia: sul filo', () => {
    expect(classifyCsrd(200, 900 * M, false)).toBe('filo')
  })
})

describe('CSRD result', () => {
  it('in ambito: data delle soglie 18 marzo 2026 e fonte Omnibus I con CELEX 32026L0470', () => {
    const r = result(company({ employees: 1500, turnoverEur: 620 * M }), 'CSRD')
    expect(r.status).toBe('in_scope')
    expect(r.from).toBe(SCOPE_DATES.omnibusInForce)
    expect(r.fromLabel).toContain('18 marzo 2026')
    expect(r.sources.some((s) => s.celex === '32026L0470' && s.url?.includes('32026L0470'))).toBe(true)
    expect(r.reasons.join(' ')).toContain('1.500')
  })
  it('in English: British dates, English separators and the official act names', () => {
    const r = result(company({ employees: 1500, turnoverEur: 620 * M }), 'CSRD', en)
    expect(r.status).toBe('in_scope')
    expect(r.fromLabel).toBe('Thresholds in force from 18 March 2026 (Omnibus I)')
    expect(r.reasons.join(' ')).toContain('Employees: 1,500 (above 1,000).')
    expect(r.reasons.join(' ')).toContain('Net turnover: 620 million euro (above 450 million euro).')
    expect(r.sources[0].act).toBe('Directive (EU) 2026/470 (Omnibus I)')
    expect(r.sources[0].url).toContain('/legal-content/EN/')
  })
  it('sul filo: stato condizionale con la ragione della soglia mancante', () => {
    const r = result(company({ employees: 1200, turnoverEur: 380 * M }), 'CSRD')
    expect(r.status).toBe('conditional')
    expect(r.reasons[0]).toMatch(/non quella dei ricavi/)
  })
  it('fuori: nessuna data di applicazione e note sulla filiera', () => {
    const r = result(company({ employees: 600, turnoverEur: 120 * M }), 'CSRD')
    expect(r.status).toBe('out_of_scope')
    expect(r.from).toBeUndefined()
    expect(r.notes.join(' ')).toMatch(/VSME/)
  })
  it('quotata sotto soglia: condizionale con la ragione della quotata', () => {
    const r = result(company({ employees: 500, turnoverEur: 100 * M, listedEu: true }), 'CSRD')
    expect(r.status).toBe('conditional')
    expect(r.reasons[0]).toMatch(/società quotata/)
  })
  it('Wave 1: la nota ricorda l’esenzione transitoria FY2025-2026', () => {
    const r = result(company({ employees: 1500, turnoverEur: 620 * M, wave1Reporter: true }), 'CSRD')
    expect(r.notes.join(' ')).toMatch(/2025 e 2026/)
  })
  it('dati mancanti: non valutato', () => {
    const r = result(company({ employees: null, turnoverEur: null }), 'CSRD')
    expect(r.status).toBe('not_assessed')
  })
  it('impresa extra-UE con ricavi UE oltre 450 M€: condizionale; sotto: fuori', () => {
    const over = result(company({ nonEu: true, euTurnoverEur: 500 * M }), 'CSRD')
    expect(over.status).toBe('conditional')
    const under = result(company({ nonEu: true, euTurnoverEur: 300 * M }), 'CSRD')
    expect(under.status).toBe('out_of_scope')
    const missing = result(company({ nonEu: true, euTurnoverEur: null }), 'CSRD')
    expect(missing.status).toBe('not_assessed')
  })
})

describe('CSDDD result', () => {
  it('oltre 5.000 dipendenti e 1,5 mld€: in ambito dal 26 luglio 2029', () => {
    const r = result(company({ employees: 6000, turnoverEur: 2000 * M }), 'CSDDD')
    expect(r.status).toBe('in_scope')
    expect(r.from).toBe('2029-07-26')
    expect(r.reasons.join(' ')).toContain('26 luglio 2028')
    expect(r.reasons.join(' ')).toContain('26 luglio 2029')
  })
  it('una sola soglia superata: fuori dalle soglie dirette (regola cumulativa)', () => {
    const r = result(company({ employees: 6000, turnoverEur: 1400 * M }), 'CSDDD')
    expect(r.status).toBe('out_of_scope')
    expect(r.reasons[0]).toMatch(/una sola/)
  })
  it('1.500 dipendenti e 620 M€: in ambito CSRD ma fuori CSDDD', () => {
    const r = result(company({ employees: 1500, turnoverEur: 620 * M }), 'CSDDD')
    expect(r.status).toBe('out_of_scope')
  })
  it('impresa extra-UE: non valutato, perché le fonti non riportano le soglie', () => {
    const r = result(company({ nonEu: true, euTurnoverEur: 500 * M }), 'CSDDD')
    expect(r.status).toBe('not_assessed')
  })
})

describe('AI Act art. 50 result (port of public/scope-aiact.html)', () => {
  it('domande non risposte: non valutato, mai un falso negativo', () => {
    const r = result(company({ ai: null }), 'AI_ACT')
    expect(r.status).toBe('not_assessed')
  })
  it('nessuna delle quattro: fuori dall’art. 50, con le note su art. 4, art. 5, GPAI e alto rischio', () => {
    const r = result(company({ ai: NO_AI }), 'AI_ACT')
    expect(r.status).toBe('out_of_scope')
    expect(r.notes.join(' ')).toContain('2 febbraio 2025')
    expect(r.notes.join(' ')).toContain('2 dicembre 2027')
    expect(r.notes.join(' ')).toContain('2 agosto 2028')
  })
  it('solo un chatbot: in ambito dal 2 agosto 2026, obbligo del fornitore, art. 50 par. 1 con passaggio testuale', () => {
    const r = result(company({ ai: keysToAi(['chat']) }), 'AI_ACT')
    expect(r.status).toBe('in_scope')
    expect(r.from).toBe('2026-08-02')
    expect(r.obligations?.map((o) => o.key)).toEqual(['chat'])
    expect(r.obligations?.[0].who).toBe('provider')
    expect(r.passages).toHaveLength(1)
    expect(r.passages[0].article).toBe('art. 50, par. 1')
    expect(r.passages[0].lang).toBe('it')
    expect(r.sources[0].article).toBe('art. 50, par. 1')
    expect(r.sources.some((s) => s.article?.startsWith('art. 113'))).toBe(true)
  })
  it('in English the quoted passage stays Italian while the act and the article follow the reader', () => {
    const r = result(company({ ai: keysToAi(['chat']) }), 'AI_ACT', en)
    expect(r.headline).toBe('From 2 August 2026 Art. 50 covers the situations you indicated.')
    expect(r.passages[0].quote).toBe('siano informate del fatto che stanno interagendo con un sistema di IA')
    expect(r.passages[0].lang).toBe('it')
    expect(r.passages[0].act).toBe('Regulation (EU) 2024/1689')
    expect(r.passages[0].article).toBe('Art. 50(1)')
    expect(r.obligations?.[0].whoLabel).toBe('Provider obligation')
  })
  it('chatbot e GenAI: due obblighi del fornitore, par. 1 e par. 2', () => {
    const r = result(company({ ai: keysToAi(['chat', 'gen']) }), 'AI_ACT')
    expect(r.obligations?.map((o) => o.article)).toEqual(['art. 50, par. 1', 'art. 50, par. 2'])
    expect(r.obligations?.every((o) => o.who === 'provider')).toBe(true)
  })
  it('emozioni e deepfake: obblighi dell’utilizzatore, par. 3 e par. 4, senza passaggio testuale', () => {
    const r = result(company({ ai: keysToAi(['emo', 'deep']) }), 'AI_ACT')
    expect(r.obligations?.map((o) => o.who)).toEqual(['deployer', 'deployer'])
    expect(r.obligations?.map((o) => o.article)).toEqual(['art. 50, par. 3', 'art. 50, par. 4'])
    expect(r.passages).toHaveLength(0)
  })
  it('la nota sul transitorio GenAI cita il 2 dicembre 2026', () => {
    expect(aiObligations(it_).gen.exception).toContain('2 dicembre 2026')
    expect(aiObligations(en).gen.exception).toContain('2 December 2026')
  })
})

describe('every result', () => {
  it('carries verifiedOn 2026-10-23 and at least one source with a link', () => {
    const inputs: ScopeInput[] = [
      company({ employees: 1500, turnoverEur: 620 * M, ai: keysToAi(['chat']) }),
      company({ employees: 600, turnoverEur: 120 * M, ai: NO_AI }),
      company({ nonEu: true, euTurnoverEur: 500 * M }),
      company({}),
    ]
    for (const ctx of [it_, en]) {
      for (const input of inputs) {
        const assessment = assessScope(input, ctx)
        expect(assessment.verifiedOn).toBe(VERIFIED_ON)
        expect(assessment.results).toHaveLength(3)
        for (const r of assessment.results) {
          expect(r.verifiedOn).toBe('2026-10-23')
          expect(r.sources.length).toBeGreaterThan(0)
          expect(r.sources.some((s) => s.url)).toBe(true)
          expect(r.sources.map((s) => s.index)).toEqual(r.sources.map((_, i) => i + 1))
        }
      }
    }
  })
})
