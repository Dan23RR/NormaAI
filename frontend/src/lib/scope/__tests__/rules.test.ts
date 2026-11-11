import { describe, it, expect } from 'vitest'
import {
  RULE_SOURCES,
  SCOPE_DATES,
  SCOPE_FRAMEWORKS,
  aiObligations,
  assessScope,
  classifyCsrd,
  nisCategory,
  nisSizeClass,
} from '../rules'
import { EMPTY_INPUT, NO_AI, NO_MACHINERY, NO_NIS, NO_WORK_AI, keysToAi, keysToMachinery, keysToWork } from '../query'
import { dateWithArticle, verificationLabel } from '../sources'
import { assessmentCheckedOn, assessmentToText, byRelevance } from '../text'
import type { NisSector, ScopeInput, ScopeResult } from '../types'
import { NIS_ANNEX_I, NIS_ANNEX_II } from '../types'
import { verifiedOn } from '@/lib/verification'
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

function ids(r: ScopeResult): string[] {
  return r.sources.map((s) => s.id)
}

function duties(r: ScopeResult): string[] {
  return (r.obligations ?? []).map((o) => o.key)
}

function nis(sector: NisSector, flags: { anySize?: boolean; linked?: boolean } = {}) {
  return { ...NO_NIS, sector, ...flags }
}

describe('classifyCsrd', () => {
  it('600 dipendenti e 120 M€: fuori', () => {
    expect(classifyCsrd(600, 120 * M, false)).toBe('out')
  })
  it('1.200 dipendenti e 380 M€: una sola soglia superata, sul filo', () => {
    expect(classifyCsrd(1200, 380 * M, false)).toBe('filo')
  })
  it('1.500 dipendenti e 620 M€: in ambito', () => {
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
  it('in ambito: esercizi dal 1 gennaio 2027, con soglie, direttiva e decreto italiano tra le fonti', () => {
    const r = result(company({ employees: 1500, turnoverEur: 620 * M }), 'CSRD')
    expect(r.status).toBe('in_scope')
    expect(r.from).toBe(SCOPE_DATES.csrdFirstYear)
    expect(r.fromLabel).toContain('1 gennaio 2027')
    expect(r.reasons.join(' ')).toContain('1.500')
    expect(r.reasons[0]).toContain('art. 19 bis')
    expect(ids(r)).toEqual(['dir-2013-34-19bis-1', 'csrd-5-2-b', 'dlgs-125-2024-17-1-b'])
    expect(r.sources[0].celex).toBe('32013L0034')
    expect(r.sources[0].url).toContain('02013L0034-')
  })
  it('in English: British dates, English separators, the official act names and English article labels', () => {
    const r = result(company({ employees: 1500, turnoverEur: 620 * M }), 'CSRD', en)
    expect(r.status).toBe('in_scope')
    expect(r.fromLabel).toBe('New scope: financial years starting from 1 January 2027 (Directive (EU) 2022/2464, Art. 5(2))')
    expect(r.reasons.join(' ')).toContain('Employees: 1,500 (above 1,000).')
    expect(r.reasons.join(' ')).toContain('Net turnover: 620 million euro (above 450 million euro).')
    expect(r.sources[0].act).toBe('Directive 2013/34/EU (Accounting Directive), as amended by Directive (EU) 2026/470')
    expect(r.sources[0].article).toBe('Art. 19a(1)')
    expect(r.sources[0].url).toContain('/legal-content/EN/')
  })
  it('sul filo per i dipendenti: condizionale, senza la nota sulle imprese protette', () => {
    const r = result(company({ employees: 1200, turnoverEur: 380 * M }), 'CSRD')
    expect(r.status).toBe('conditional')
    expect(r.from).toBeUndefined()
    expect(r.reasons[0]).toMatch(/non quella dei ricavi/)
    expect(r.notes.join(' ')).not.toMatch(/impresa protetta/)
    expect(ids(r)).not.toContain('dir-2013-34-19bis-3-protetta')
    expect(ids(r)).toContain('dlgs-125-2024-17-3bis')
  })
  it('sul filo per i ricavi: la ragione dei dipendenti mancanti e la nota sulle imprese protette', () => {
    const r = result(company({ employees: 200, turnoverEur: 900 * M }), 'CSRD')
    expect(r.status).toBe('conditional')
    expect(r.reasons[0]).toMatch(/non quella dei dipendenti/)
    expect(r.notes.join(' ')).toMatch(/impresa protetta/)
    expect(ids(r)).toContain('dir-2013-34-19bis-3-rifiuto')
  })
  it('a ridosso di una soglia: condizionale con la ragione del margine', () => {
    const r = result(company({ employees: 900, turnoverEur: 100 * M }), 'CSRD')
    expect(r.status).toBe('conditional')
    expect(r.reasons[0]).toMatch(/a ridosso di una soglia/)
  })
  it('quotata sotto soglia: condizionale con la ragione della quotata', () => {
    const r = result(company({ employees: 500, turnoverEur: 100 * M, listedEu: true }), 'CSRD')
    expect(r.status).toBe('conditional')
    expect(r.reasons[0]).toMatch(/società quotata/)
  })
  it('fuori: nessuna data, esclusione italiana 2026-2027 e diritto delle imprese protette', () => {
    const r = result(company({ employees: 600, turnoverEur: 120 * M }), 'CSRD')
    expect(r.status).toBe('out_of_scope')
    expect(r.from).toBeUndefined()
    expect(r.notes.join(' ')).toContain('art. 17, comma 3-bis')
    expect(r.notes.join(' ')).toMatch(/impresa protetta/)
    expect(ids(r)).toEqual([
      'dir-2013-34-19bis-1',
      'dlgs-125-2024-17-3bis',
      'dir-2013-34-19bis-3-protetta',
      'dir-2013-34-19bis-3-rifiuto',
    ])
  })
  it('già in rendicontazione: la nota cita la norma italiana e la facoltà degli Stati membri', () => {
    const r = result(company({ employees: 700, turnoverEur: 200 * M, wave1Reporter: true }), 'CSRD')
    expect(r.notes.join(' ')).toMatch(/facoltà di esentare gli esercizi 2025 e 2026/)
    expect(ids(r)).toEqual(expect.arrayContaining(['csrd-5-2-a', 'csrd-5-2-esenzione', 'dlgs-125-2024-17-3bis']))
  })
  it('capogruppo: soglie su base consolidata (art. 29 bis); controllata: verifica sul gruppo', () => {
    const parent = result(company({ employees: 1500, turnoverEur: 620 * M, groupRole: 'parent' }), 'CSRD')
    expect(parent.notes.join(' ')).toContain('art. 29 bis')
    expect(ids(parent)).toContain('dir-2013-34-29bis-1')
    const subsidiary = result(company({ employees: 1500, turnoverEur: 620 * M, groupRole: 'subsidiary' }), 'CSRD')
    expect(subsidiary.notes.join(' ')).toMatch(/capogruppo/)
    expect(ids(subsidiary)).not.toContain('dir-2013-34-29bis-1')
  })
  it('dati mancanti: non valutato', () => {
    const r = result(company({ employees: null, turnoverEur: null }), 'CSRD')
    expect(r.status).toBe('not_assessed')
    expect(r.reasons).toEqual([])
  })
  it('impresa extra-UE: oltre 450 M€ nell’Unione condizionale, sotto fuori, senza dato non valutato', () => {
    const over = result(company({ nonEu: true, euTurnoverEur: 500 * M }), 'CSRD')
    expect(over.status).toBe('conditional')
    expect(over.reasons.join(' ')).toContain('art. 40 bis')
    expect(over.reasons.join(' ')).toContain('200 milioni di euro')
    expect(ids(over)).toEqual(['dir-2013-34-40bis-1-ue', 'dir-2013-34-40bis-1-figlia'])
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
    expect(r.notes.join(' ')).toContain('due esercizi consecutivi')
    expect(r.notes.join(' ')).toContain('3%')
    expect(r.notes.join(' ')).toContain('26 luglio 2027')
    expect(ids(r)).toEqual([
      'csddd-2-1-a',
      'csddd-37-1-recepimento',
      'csddd-37-1-applicazione',
      'csddd-2-5',
      'csddd-27-4',
      'csddd-19-3',
    ])
  })
  it('una sola soglia superata: fuori dalle soglie dirette (regola cumulativa)', () => {
    const r = result(company({ employees: 6000, turnoverEur: 1400 * M }), 'CSDDD')
    expect(r.status).toBe('out_of_scope')
    expect(r.reasons[0]).toMatch(/una sola/)
  })
  it('1.500 dipendenti e 620 M€: fuori, con la tutela dei partner sotto 5.000 dipendenti', () => {
    const r = result(company({ employees: 1500, turnoverEur: 620 * M }), 'CSDDD')
    expect(r.status).toBe('out_of_scope')
    expect(r.reasons[0]).toMatch(/Non superi le soglie cumulative/)
    expect(r.notes[0]).toContain('meno di 5.000 dipendenti')
    expect(ids(r)).toContain('csddd-8-2bis-a')
  })
  it('impresa extra-UE: soglia di 1,5 mld€ di fatturato nell’Unione', () => {
    const over = result(company({ nonEu: true, euTurnoverEur: 1600 * M }), 'CSDDD')
    expect(over.status).toBe('in_scope')
    expect(over.from).toBe('2029-07-26')
    expect(ids(over)[0]).toBe('csddd-2-2-a')
    const under = result(company({ nonEu: true, euTurnoverEur: 500 * M }), 'CSDDD')
    expect(under.status).toBe('out_of_scope')
    expect(under.reasons[0]).toContain('1,5 miliardi di euro')
    const missing = result(company({ nonEu: true }), 'CSDDD')
    expect(missing.status).toBe('not_assessed')
  })
  it('dati mancanti: non valutato', () => {
    expect(result(company({}), 'CSDDD').status).toBe('not_assessed')
  })
})

describe('AI Act art. 50 result', () => {
  it('domande non risposte: non valutato, mai un falso negativo', () => {
    const r = result(company({ ai: null }), 'AI_ACT')
    expect(r.status).toBe('not_assessed')
  })
  it('nessuna delle quattro: fuori dall’art. 50, con le note su art. 4, art. 5, GPAI e alto rischio', () => {
    const r = result(company({ ai: NO_AI }), 'AI_ACT')
    expect(r.status).toBe('out_of_scope')
    const notes = r.notes.join(' ')
    expect(notes).toContain('2 febbraio 2025')
    expect(notes).toContain('2 dicembre 2026')
    expect(notes).toContain('2 agosto 2025')
    expect(notes).toContain('2 dicembre 2027')
    expect(notes).toContain('2 agosto 2028')
    expect(ids(r)).toEqual(expect.arrayContaining(['ai-act-4-1', 'ai-act-113-a', 'ai-act-53-1', 'ai-act-113-c-i', 'ai-act-113-c-ii']))
  })
  it('solo un chatbot: in ambito dal 2 agosto 2026, obbligo del fornitore, art. 50 par. 1 con il passaggio ufficiale', () => {
    const r = result(company({ ai: keysToAi(['chat']) }), 'AI_ACT')
    expect(r.status).toBe('in_scope')
    expect(r.from).toBe('2026-08-02')
    expect(r.obligations?.map((o) => o.key)).toEqual(['chat'])
    expect(r.obligations?.[0].who).toBe('provider')
    expect(r.obligations?.[0].article).toBe('art. 50, par. 1')
    expect(r.sources[0].article).toBe('art. 50, par. 1')
    expect(r.sources[0].quote).toContain('siano informate del fatto di stare interagendo con un sistema di IA')
    expect(r.sources.some((s) => s.article?.startsWith('art. 113'))).toBe(true)
    expect(r.notes.join(' ')).toContain('15 milioni di euro')
    expect(r.notes.join(' ')).toContain('AgID e ACN')
  })
  it('in English the quoted passage stays Italian while the act and the article follow the reader', () => {
    const r = result(company({ ai: keysToAi(['chat']) }), 'AI_ACT', en)
    expect(r.headline).toBe('Art. 50, applicable from 2 August 2026, covers the situations you indicated.')
    expect(r.sources[0].quote).toContain('siano informate del fatto di stare interagendo con un sistema di IA')
    expect(r.sources[0].act).toBe('Regulation (EU) 2024/1689 (AI Act)')
    expect(r.sources[0].article).toBe('Art. 50(1)')
    expect(r.obligations?.[0].whoLabel).toBe('Provider obligation')
  })
  it('chatbot e GenAI: due obblighi del fornitore, par. 1 e par. 2, e la fonte del termine transitorio', () => {
    const r = result(company({ ai: keysToAi(['chat', 'gen']) }), 'AI_ACT')
    expect(r.obligations?.map((o) => o.article)).toEqual(['art. 50, par. 1', 'art. 50, par. 2'])
    expect(r.obligations?.every((o) => o.who === 'provider')).toBe(true)
    expect(ids(r)).toContain('ai-act-111-4')
  })
  it('emozioni e deepfake: obblighi dell’utilizzatore, par. 3 e par. 4, e il divieto sul luogo di lavoro tra le fonti', () => {
    const r = result(company({ ai: keysToAi(['emo', 'deep']) }), 'AI_ACT')
    expect(r.obligations?.map((o) => o.who)).toEqual(['deployer', 'deployer'])
    expect(r.obligations?.map((o) => o.article)).toEqual(['art. 50, par. 3', 'art. 50, par. 4'])
    expect(ids(r)).toContain('ai-act-5-1-f')
  })
  it('la nota sul transitorio GenAI cita il 2 dicembre 2026 e il divieto il 2 febbraio 2025', () => {
    expect(aiObligations(it_).gen.exception).toContain('2 dicembre 2026')
    expect(aiObligations(it_).gen.exception).toContain('2 agosto 2026')
    expect(aiObligations(en).gen.exception).toContain('2 December 2026')
    expect(aiObligations(it_).emo.exception).toContain('2 febbraio 2025')
  })
})

describe('AI nei rapporti di lavoro', () => {
  it('domande non risposte: non valutato', () => {
    expect(result(company({}), 'AI_WORK').status).toBe('not_assessed')
  })
  it('nessuna situazione: fuori, con l’invito a rifare la verifica', () => {
    const r = result(company({ work: NO_WORK_AI }), 'AI_WORK')
    expect(r.status).toBe('out_of_scope')
    expect(r.obligations).toBeUndefined()
    expect(r.notes[0]).toContain('D.Lgs. 179/2026')
  })
  it('decisioni sul personale: art. 41, informativa, alto rischio dal 2 dicembre 2027, formazione e alfabetizzazione', () => {
    const r = result(company({ work: keysToWork(['dec']) }), 'AI_WORK')
    expect(r.status).toBe('in_scope')
    expect(r.from).toBe('2026-10-23')
    expect(r.fromLabel).toContain('23 ottobre 2026')
    expect(duties(r)).toEqual(['decisions', 'information', 'highRisk', 'training', 'literacy'])
    const byKey = Object.fromEntries((r.obligations ?? []).map((o) => [o.key, o]))
    expect(byKey.decisions.article).toBe('art. 41, comma 1')
    expect(byKey.decisions.requirement).toContain('persona fisica')
    expect(byKey.decisions.exception).toContain('nulli')
    expect(byKey.information.article).toBe('art. 41, comma 3')
    expect(byKey.highRisk.article).toBe('art. 26, par. 7')
    expect(byKey.highRisk.exception).toContain('2 dicembre 2027')
    expect(byKey.literacy.who).toBe('deployer')
    expect(r.notes.join(' ')).toContain('selezione delle candidature')
    expect(r.notes.join(' ')).toContain('art. 11, comma 2')
    expect(ids(r)).toEqual(
      expect.arrayContaining([
        'dlgs-179-2026-41-1',
        'dlgs-179-2026-41-1-selezione',
        'dlgs-179-2026-41-4',
        'dlgs-179-2026-41-3',
        'dlgs-152-1997-1bis-1',
        'dlgs-152-1997-1bis-6',
        'legge-132-2025-11-2',
        'ai-act-26-7',
        'ai-act-annex-iii-4',
        'ai-act-113-c-i',
      ]),
    )
  })
  it('organizzazione e sicurezza: art. 42, valutazione dei rischi e formazione', () => {
    const r = result(company({ work: keysToWork(['org']) }), 'AI_WORK')
    expect(r.status).toBe('in_scope')
    expect(r.from).toBe('2026-10-23')
    expect(duties(r)).toEqual(['riskAssessment', 'training', 'literacy'])
    expect(r.obligations?.[0].article).toBe('art. 42, comma 2')
    expect(r.obligations?.[0].requirement).toContain('art. 28 del D.Lgs. 81/2008')
    expect(r.notes.join(' ')).not.toContain('selezione delle candidature')
  })
  it('solo uso da parte del personale: formazione e alfabetizzazione, senza la data del decreto', () => {
    const r = result(company({ work: keysToWork(['uso']) }), 'AI_WORK')
    expect(r.status).toBe('in_scope')
    expect(r.from).toBeUndefined()
    expect(r.fromLabel).toBeUndefined()
    expect(duties(r)).toEqual(['training', 'literacy'])
    expect(r.obligations?.[1].exception).toContain('2 febbraio 2025')
    expect(r.notes).toEqual([])
  })
  it('studio professionale: informare il cliente (legge 132/2025, art. 13)', () => {
    const r = result(company({ work: keysToWork(['prof']) }), 'AI_WORK')
    expect(duties(r)).toEqual(['literacy', 'clients'])
    const clients = r.obligations?.find((o) => o.key === 'clients')
    expect(clients?.who).toBe('professional')
    expect(clients?.article).toBe('art. 13, comma 2')
    expect(clients?.exception).toContain('art. 13, comma 1')
    expect(ids(r)).toEqual(expect.arrayContaining(['legge-132-2025-13-2', 'legge-132-2025-13-1']))
  })
  it('emozioni dei lavoratori: pratica vietata, detto nel titolo del risultato', () => {
    const r = result(company({ work: keysToWork(['emo']) }), 'AI_WORK')
    expect(r.status).toBe('in_scope')
    expect(r.headline).toMatch(/pratica vietata/)
    expect(duties(r)).toEqual(['emotions'])
    expect(r.obligations?.[0].article).toBe('art. 5, par. 1, lett. f)')
    expect(r.obligations?.[0].exception).toContain('2 febbraio 2025')
  })
  it('in English: employer duties with English article labels', () => {
    const r = result(company({ work: keysToWork(['dec']) }), 'AI_WORK', en)
    expect(r.fromLabel).toBe('Legislative Decree 179/2026, Articles 41 and 42, in force from 23 October 2026')
    expect(r.obligations?.[0].whoLabel).toBe('Employer obligation')
    expect(r.obligations?.[0].article).toBe('Art. 41(1)')
    expect(r.sources[0].act).toBe('Italian Legislative Decree No 179 of 7 October 2026')
    expect(r.sources[0].origin).toBe('Normattiva')
    expect(r.sources[0].url).toContain('normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2026-10-07;179~art41')
  })
})

describe('NIS: classe dimensionale (raccomandazione 2003/361/CE)', () => {
  it('50 persone bastano a superare i massimali delle piccole imprese', () => {
    expect(nisSizeClass(50, 1 * M, 1 * M)).toBe('not_small')
    expect(nisSizeClass(49, 1 * M, 1 * M)).toBe('small')
  })
  it('sotto 50 persone è piccola se ricavi o totale di bilancio non superano 10 M€', () => {
    expect(nisSizeClass(30, 10 * M, 40 * M)).toBe('small')
    expect(nisSizeClass(30, 40 * M, 10 * M)).toBe('small')
    expect(nisSizeClass(30, 5 * M, null)).toBe('small')
    expect(nisSizeClass(30, 10.1 * M, 10.1 * M)).toBe('not_small')
  })
  it('ricavi e bilancio entrambi oltre 10 M€ bastano anche senza il numero di dipendenti', () => {
    expect(nisSizeClass(null, 15 * M, 12 * M)).toBe('not_small')
  })
  it('resta indeterminata quando i dati non bastano', () => {
    expect(nisSizeClass(30, 15 * M, null)).toBe('unknown')
    expect(nisSizeClass(30, null, 12 * M)).toBe('unknown')
    expect(nisSizeClass(30, null, null)).toBe('unknown')
    expect(nisSizeClass(null, 5 * M, null)).toBe('unknown')
    expect(nisSizeClass(null, null, null)).toBe('unknown')
  })
  it('categoria: essenziale solo per l’allegato I sopra i massimali delle medie imprese', () => {
    expect(nisCategory('energia', 250, 1 * M, 1 * M)).toBe('essential')
    expect(nisCategory('energia', 100, 60 * M, 44 * M)).toBe('essential')
    expect(nisCategory('energia', 100, 60 * M, 43 * M)).toBe('important')
    expect(nisCategory('energia', 100, 50 * M, 90 * M)).toBe('important')
    expect(nisCategory('energia', 100, 60 * M, null)).toBe('depends')
    expect(nisCategory('energia', null, 20 * M, 20 * M)).toBe('depends')
    expect(nisCategory('fabbricazione', 3000, 900 * M, 900 * M)).toBe('important')
  })
})

describe('NIS result (D.Lgs. 138/2024)', () => {
  it('settore non indicato: non valutato', () => {
    expect(result(company({ employees: 300, turnoverEur: 80 * M }), 'NIS2').status).toBe('not_assessed')
  })
  it('nessun settore degli allegati: fuori, con le note su individuazione e catena di approvvigionamento', () => {
    const r = result(company({ employees: 300, turnoverEur: 80 * M, nis: NO_NIS }), 'NIS2')
    expect(r.status).toBe('out_of_scope')
    expect(r.notes.join(' ')).toContain('art. 3, comma 9')
    expect(r.notes.join(' ')).toContain('art. 24, comma 2, lett. d)')
    expect(r.obligations).toBeUndefined()
  })
  it('manifattura con 60 dipendenti: in ambito come soggetto importante, con i quattro obblighi e le date', () => {
    const r = result(company({ employees: 60, turnoverEur: 12 * M, nis: nis('fabbricazione') }), 'NIS2')
    expect(r.status).toBe('in_scope')
    expect(r.reasons[0]).toContain('allegato II')
    expect(r.reasons[1]).toContain('meno di 50 persone')
    expect(r.reasons[1]).toContain('10 milioni di euro')
    expect(r.notes.join(' ')).toContain('soggetto importante')
    expect(r.notes.join(' ')).toContain('7 milioni di euro')
    expect(duties(r)).toEqual(['register', 'governance', 'measures', 'incidents', 'activities'])
    const byKey = Object.fromEntries((r.obligations ?? []).map((o) => [o.key, o]))
    expect(byKey.register.article).toBe('art. 7, comma 1')
    expect(byKey.register.requirement).toContain('Dal 1 gennaio al 28 febbraio')
    expect(byKey.measures.exception).toContain('31 luglio 2027')
    expect(byKey.measures.exception).toContain('diciotto mesi')
    expect(byKey.incidents.requirement).toContain('24 ore')
    expect(byKey.incidents.requirement).toContain('72 ore')
    expect(byKey.incidents.exception).toContain('1 gennaio 2027')
    expect(byKey.incidents.exception).toContain('nove mesi')
    expect(byKey.incidents.exception).toContain('referente CSIRT')
    expect(byKey.activities.article).toBe('art. 30, comma 1')
    expect(byKey.activities.requirement).toContain('Dal 1 maggio al 30 giugno')
    expect(ids(r)).toEqual(
      expect.arrayContaining([
        'dlgs-138-2024-allegato-2',
        'dlgs-138-2024-allegato-2-fabbricazione',
        'dlgs-138-2024-3-2',
        'rec-2003-361-2-2',
        'dlgs-138-2024-7-1',
        'dlgs-138-2024-23-1',
        'dlgs-138-2024-24-1',
        'dlgs-138-2024-25-5',
        'acn-det-127434-2026-1-1',
        'acn-det-127434-2026-1-2',
        'acn-det-379907-2025-3-1',
        'acn-det-379907-2025-3-2',
        'acn-det-314287-2026-7-1',
        'dlgs-138-2024-30-1',
        'dlgs-138-2024-38-9',
      ]),
    )
    expect(r.sources.find((s) => s.id === 'acn-det-127434-2026-1-1')?.origin).toBe('ACN')
  })
  it('allegato I oltre i massimali delle medie imprese: categoria probabile essenziale', () => {
    const r = result(company({ employees: 300, turnoverEur: 80 * M, nis: nis('energia') }), 'NIS2')
    expect(r.status).toBe('in_scope')
    expect(r.reasons[0]).toContain('allegato I')
    expect(r.notes.join(' ')).toContain('soggetto essenziale')
    expect(ids(r)).toEqual(expect.arrayContaining(['dlgs-138-2024-allegato-1', 'rec-2003-361-2-1', 'dlgs-138-2024-6-1']))
  })
  it('allegato I media impresa: importante; con bilancio mancante la categoria dipende', () => {
    const medium = result(company({ employees: 100, turnoverEur: 30 * M, nis: nis('sanita') }), 'NIS2')
    expect(medium.notes.join(' ')).toContain('soggetto importante')
    const depends = result(company({ employees: 100, turnoverEur: 60 * M, nis: nis('sanita') }), 'NIS2')
    expect(depends.notes.join(' ')).toContain('43 milioni')
  })
  it('piccola impresa in un settore NIS: fuori per dimensione', () => {
    const r = result(company({ employees: 30, turnoverEur: 5 * M, nis: nis('alimenti') }), 'NIS2')
    expect(r.status).toBe('out_of_scope')
    expect(r.headline).toMatch(/piccole imprese/)
    expect(r.reasons[1]).toContain('art. 3, comma 2')
    expect(r.obligations).toBeUndefined()
  })
  it('meno di 50 dipendenti e ricavi oltre 10 M€: dipende dal totale di bilancio', () => {
    const open = result(company({ employees: 30, turnoverEur: 15 * M, nis: nis('chimica') }), 'NIS2')
    expect(open.status).toBe('conditional')
    expect(open.reasons[1]).toMatch(/Indica il totale di bilancio/)
    const over = result(company({ employees: 30, turnoverEur: 15 * M, balanceSheetEur: 12 * M, nis: nis('chimica') }), 'NIS2')
    expect(over.status).toBe('in_scope')
    const under = result(company({ employees: 30, turnoverEur: 15 * M, balanceSheetEur: 8 * M, nis: nis('chimica') }), 'NIS2')
    expect(under.status).toBe('out_of_scope')
    const noTurnover = result(company({ employees: 30, balanceSheetEur: 12 * M, nis: nis('chimica') }), 'NIS2')
    expect(noTurnover.status).toBe('conditional')
    expect(noTurnover.reasons[1]).toMatch(/Indica i ricavi netti/)
  })
  it('dati dimensionali mancanti: non valutato, con ciò che serve', () => {
    const noEmployees = result(company({ turnoverEur: 5 * M, nis: nis('rifiuti') }), 'NIS2')
    expect(noEmployees.status).toBe('not_assessed')
    expect(noEmployees.headline).toMatch(/numero di dipendenti/)
    const noFinancials = result(company({ employees: 30, nis: nis('rifiuti') }), 'NIS2')
    expect(noFinancials.status).toBe('not_assessed')
    expect(noFinancials.headline).toMatch(/ricavi netti o totale di bilancio/)
  })
  it('pubblica amministrazione dell’allegato III: si applica a prescindere dalle dimensioni', () => {
    const r = result(company({ nis: nis('pa') }), 'NIS2')
    expect(r.status).toBe('in_scope')
    expect(r.reasons[0]).toContain('art. 3, comma 6')
    expect(r.notes.join(' ')).toContain('art. 7, comma 3')
    expect(ids(r)).toEqual(expect.arrayContaining(['dlgs-138-2024-3-6', 'dlgs-138-2024-allegato-3']))
  })
  it('tipologie dell’allegato IV: solo se ACN individua il soggetto', () => {
    const r = result(company({ employees: 500, turnoverEur: 90 * M, nis: nis('altri') }), 'NIS2')
    expect(r.status).toBe('conditional')
    expect(r.reasons[0]).toContain('art. 3, comma 8')
    expect(r.notes[0]).toContain('art. 3, comma 13')
    expect(ids(r)).toEqual(['dlgs-138-2024-3-8', 'dlgs-138-2024-allegato-4', 'dlgs-138-2024-3-13'])
  })
  it('fornitori considerati a prescindere dalle dimensioni: in ambito anche se piccoli', () => {
    const r = result(company({ employees: 8, turnoverEur: 1 * M, nis: nis('digitale', { anySize: true }) }), 'NIS2')
    expect(r.status).toBe('in_scope')
    expect(r.reasons[0]).toContain('art. 3, comma 5')
    expect(ids(r)[0]).toBe('dlgs-138-2024-3-5')
  })
  it('impresa collegata a un soggetto NIS: in ambito senza settore e senza soglie', () => {
    const r = result(company({ employees: 12, turnoverEur: 2 * M, nis: { ...NO_NIS, linked: true } }), 'NIS2')
    expect(r.status).toBe('in_scope')
    expect(r.reasons[0]).toContain('art. 3, comma 10')
    expect(duties(r)).toEqual(['register', 'governance', 'measures', 'incidents', 'activities'])
  })
  it('banche e mercati finanziari: dipende, con la sola registrazione e il rinvio a DORA', () => {
    for (const sector of ['banche', 'mercati'] as const) {
      const r = result(company({ employees: 400, turnoverEur: 90 * M, nis: nis(sector) }), 'NIS2')
      expect(r.status, sector).toBe('conditional')
      expect(r.headline, sector).toContain('DORA')
      expect(r.notes[0], sector).toContain('art. 3, comma 14')
      expect(duties(r), sector).toEqual(['register'])
      expect(ids(r), sector).toContain('dlgs-138-2024-3-14')
      expect(ids(r), sector).not.toContain('dlgs-138-2024-38-9')
    }
  })
  it('gruppi: la nota sui dati delle imprese collegate', () => {
    const r = result(company({ employees: 60, turnoverEur: 12 * M, groupRole: 'subsidiary', nis: nis('trasporti') }), 'NIS2')
    expect(r.notes.join(' ')).toContain('art. 3, comma 4')
    expect(ids(r)).toEqual(expect.arrayContaining(['dlgs-138-2024-3-4', 'rec-2003-361-6-2']))
  })
  it('ogni settore degli allegati I e II ha un nome e porta al suo allegato', () => {
    for (const sector of [...NIS_ANNEX_I, ...NIS_ANNEX_II]) {
      const r = result(company({ employees: 300, turnoverEur: 80 * M, nis: nis(sector) }), 'NIS2')
      expect(['in_scope', 'conditional'], sector).toContain(r.status)
      const annex = (NIS_ANNEX_I as readonly string[]).includes(sector) ? 'dlgs-138-2024-allegato-1' : 'dlgs-138-2024-allegato-2'
      expect(ids(r), sector).toContain(annex)
      expect(result(company({ employees: 300, turnoverEur: 80 * M, nis: nis(sector) }), 'NIS2', en).reasons[0], sector).toMatch(
        /^Sector of Annex I+ /,
      )
    }
  })
})

describe('Regolamento macchine', () => {
  it('ruoli non indicati: non valutato', () => {
    expect(result(company({}), 'MACHINERY').status).toBe('not_assessed')
  })
  it('nessun ruolo: fuori, con la nota sulla modifica sostanziale', () => {
    const r = result(company({ machinery: NO_MACHINERY }), 'MACHINERY')
    expect(r.status).toBe('out_of_scope')
    expect(r.notes[0]).toContain('art. 18')
    expect(r.obligations).toBeUndefined()
  })
  it('fabbricante: dal 20 gennaio 2027, conformità e quasi-macchine, con le norme di ciascun obbligo', () => {
    const r = result(company({ machinery: keysToMachinery(['fab']) }), 'MACHINERY')
    expect(r.status).toBe('in_scope')
    expect(r.from).toBe('2027-01-20')
    expect(r.fromLabel).toBe('Si applica dal 20 gennaio 2027 (art. 54)')
    expect(duties(r)).toEqual(['conformity', 'partlyCompleted'])
    expect(r.obligations?.[0].who).toBe('manufacturer')
    expect(r.obligations?.[0].article).toBe('art. 10, par. 1')
    expect(r.obligations?.[0].requirement).toContain('marcatura CE')
    expect(r.obligations?.[0].exception).toContain('10 anni')
    expect(r.obligations?.[1].article).toBe('art. 11, par. 2')
    expect(r.notes.join(' ')).toContain('direttiva 2006/42/CE')
    expect(ids(r)).toEqual([
      'mach-54',
      'mach-2-1',
      'mach-3-18',
      'mach-10-1',
      'mach-10-2',
      'mach-10-3',
      'mach-10-7',
      'mach-11-2',
      'mach-52-1',
    ])
  })
  it('importatore: solo prodotti conformi, e fabbricante se usa il proprio marchio', () => {
    const r = result(company({ machinery: keysToMachinery(['imp']) }), 'MACHINERY')
    expect(duties(r)).toEqual(['importer', 'ownBrand'])
    expect(r.obligations?.[0].article).toBe('art. 13, par. 1')
    expect(r.obligations?.[1].who).toBe('importer')
    expect(r.obligations?.[1].article).toBe('art. 17')
    expect(ids(r)).toEqual(expect.arrayContaining(['mach-3-20', 'mach-13-1', 'mach-13-2', 'mach-13-8', 'mach-17']))
  })
  it('distributore: verifiche prima di vendere, e fabbricante se usa il proprio marchio', () => {
    const r = result(company({ machinery: keysToMachinery(['dis']) }), 'MACHINERY')
    expect(duties(r)).toEqual(['distributor', 'ownBrand'])
    expect(r.obligations?.[0].article).toBe('art. 15, par. 2')
    expect(r.obligations?.[0].requirement).toContain('marcatura CE')
    expect(r.obligations?.[1].who).toBe('distributor')
    expect(ids(r)).toEqual(expect.arrayContaining(['mach-3-21', 'mach-15-1', 'mach-15-2']))
  })
  it('modifica sostanziale: chi la fa assume gli obblighi del fabbricante', () => {
    const r = result(company({ machinery: keysToMachinery(['mod']) }), 'MACHINERY')
    expect(duties(r)).toEqual(['modification'])
    expect(r.obligations?.[0].article).toBe('art. 18, primo comma')
    expect(r.obligations?.[0].exception).toContain('art. 3, punto 16)')
    expect(ids(r)).toEqual(expect.arrayContaining(['mach-18', 'mach-3-16']))
  })
  it('tutti i ruoli insieme: un obbligo per ruolo, senza doppioni', () => {
    const r = result(company({ machinery: keysToMachinery(['fab', 'imp', 'dis', 'mod']) }), 'MACHINERY')
    expect(duties(r)).toEqual(['conformity', 'partlyCompleted', 'importer', 'distributor', 'ownBrand', 'modification'])
    expect(new Set(ids(r)).size).toBe(ids(r).length)
    expect(r.reasons).toHaveLength(4)
  })
  it('in English: the date of application and the manufacturer wording', () => {
    const r = result(company({ machinery: keysToMachinery(['fab']) }), 'MACHINERY', en)
    expect(r.headline).toBe('The Machinery Regulation applies from 20 January 2027 to the roles you indicated.')
    expect(r.obligations?.[0].whoLabel).toBe('Manufacturer obligation')
    expect(r.sources[0].article).toBe('Art. 54, second paragraph')
  })
})

/** Inputs that together reach every branch of every rule set. */
const MATRIX: ScopeInput[] = [
  company({}),
  company({ employees: 1500, turnoverEur: 620 * M, groupRole: 'parent', wave1Reporter: true, ai: keysToAi(['chat', 'gen', 'emo', 'deep']) }),
  company({ employees: 600, turnoverEur: 120 * M, ai: NO_AI, work: NO_WORK_AI, nis: NO_NIS, machinery: NO_MACHINERY }),
  company({ employees: 1200, turnoverEur: 380 * M }),
  company({ employees: 6000, turnoverEur: 2000 * M, work: keysToWork(['dec', 'org', 'uso', 'prof', 'emo']) }),
  company({ nonEu: true, euTurnoverEur: 1600 * M }),
  company({ nonEu: true, euTurnoverEur: 300 * M }),
  company({ employees: 60, turnoverEur: 12 * M, groupRole: 'subsidiary', nis: nis('fabbricazione') }),
  company({ employees: 300, turnoverEur: 80 * M, nis: nis('energia') }),
  company({ employees: 30, turnoverEur: 5 * M, nis: nis('alimenti') }),
  company({ employees: 30, turnoverEur: 15 * M, nis: nis('chimica') }),
  company({ employees: 400, turnoverEur: 90 * M, nis: nis('banche') }),
  company({ nis: nis('pa') }),
  company({ nis: nis('altri') }),
  company({ nis: nis('digitale', { anySize: true }) }),
  company({ nis: { ...NO_NIS, linked: true } }),
  company({ machinery: keysToMachinery(['fab', 'imp', 'dis', 'mod']) }),
]

describe('every result', () => {
  it('comes for the six rule sets, in the same order, in both languages', () => {
    for (const ctx of [it_, en]) {
      for (const input of MATRIX) {
        const assessment = assessScope(input, ctx)
        expect(assessment.results.map((r) => r.framework)).toEqual(SCOPE_FRAMEWORKS)
        expect(assessment.input).toBe(input)
      }
    }
  })

  it('points to registry sources that are verified, dated, linked and quoted', () => {
    for (const ctx of [it_, en]) {
      for (const input of MATRIX) {
        for (const r of assessScope(input, ctx).results) {
          expect(r.sources.length, r.framework).toBeGreaterThan(0)
          expect(r.sources.map((s) => s.index)).toEqual(r.sources.map((_, i) => i + 1))
          for (const s of r.sources) {
            expect(s.status, s.id).toBe('verified')
            expect(s.verifiedAt, s.id).toBe(verifiedOn(s.id))
            expect(s.url, s.id).toMatch(/^https:\/\//)
            expect((s.quote ?? '').length, s.id).toBeGreaterThanOrEqual(20)
            expect(s.act.length, s.id).toBeGreaterThan(0)
            expect((s.article ?? '').length, s.id).toBeGreaterThan(0)
          }
          for (const o of r.obligations ?? []) {
            expect(r.sources.map((s) => s.id), `${r.framework} ${o.key}`).toContain(o.source.id)
            expect(o.article).toBe(o.source.article)
          }
        }
      }
    }
  })

  it('together cite every provision of RULE_SOURCES: none is declared and never used', () => {
    const cited = new Set<string>()
    for (const input of MATRIX) {
      for (const r of assessScope(input, it_).results) for (const s of r.sources) cited.add(s.id)
    }
    expect((Object.values(RULE_SOURCES) as string[]).filter((id) => !cited.has(id))).toEqual([])
  })

  it('shows nothing internal: no guide cited as a legal basis, no file path, no pending note', () => {
    for (const ctx of [it_, en]) {
      for (const input of MATRIX) {
        const text = assessmentToText(assessScope(input, ctx), ctx)
        expect(text).not.toMatch(/\bCodex\b|\bADR-?\d|\bprompts?\b|\.planning|riga \d|\.txt|\.tsx?\b|da confermare|to be confirmed|non confermat|not confirmed/i)
      }
    }
  })
})

describe('what is shown about verification', () => {
  it('puts the Italian article before the date and elides it before 1, 8 and 11', () => {
    expect(dateWithArticle('2026-12-02', it_)).toBe('il 2 dicembre 2026')
    expect(dateWithArticle('2026-11-11', it_)).toBe('l’11 novembre 2026')
    expect(dateWithArticle('2027-01-01', it_)).toBe('l’1 gennaio 2027')
    expect(dateWithArticle('2027-03-08', it_)).toBe('l’8 marzo 2027')
    expect(dateWithArticle('2026-11-11', en)).toBe('11 November 2026')
  })

  it('says "Verificata il <date>" with the date of the check, and the consolidated text for EU acts', () => {
    const eu = result(company({ machinery: keysToMachinery(['fab']) }), 'MACHINERY').sources[0]
    const checked = verifiedOn('mach-54') as string
    expect(verificationLabel(eu, it_)).toBe(`Verificata ${dateWithArticle(checked, it_)} sul testo consolidato al 27 luglio 2026`)
    const italian = result(company({ work: keysToWork(['dec']) }), 'AI_WORK').sources[0]
    expect(verificationLabel(italian, it_)).toBe(`Verificata ${dateWithArticle(verifiedOn(italian.id) as string, it_)}`)
    expect(verificationLabel(italian, en)).toBe(`Verified on ${dateWithArticle(verifiedOn(italian.id) as string, en)}`)
  })

  it('says "Fonte indicata, non ancora verificata" for anything else', () => {
    const source = result(company({ machinery: keysToMachinery(['fab']) }), 'MACHINERY').sources[0]
    expect(verificationLabel({ ...source, status: 'unverified', verifiedAt: undefined }, it_)).toBe('Fonte indicata, non ancora verificata')
    expect(verificationLabel({ ...source, status: 'pending' }, it_)).toBe('Fonte indicata, non ancora verificata')
    expect(verificationLabel({ ...source, status: 'verified', verifiedAt: undefined }, en)).toBe('Source indicated, not yet verified')
  })
})

describe('copied result', () => {
  const input = company({
    name: 'Officine Esempio Srl',
    employees: 60,
    turnoverEur: 12 * M,
    nis: nis('fabbricazione'),
    work: keysToWork(['uso']),
    machinery: keysToMachinery(['fab']),
  })

  it('opens with the date of the check, the profile and the disclaimer', () => {
    const assessment = assessScope(input, it_)
    const lines = assessmentToText(assessment, it_).split('\n')
    const checked = assessmentCheckedOn(assessment) as string
    expect(lines[0]).toBe(`Ambito NormaAI, fonti controllate sul testo ufficiale ${dateWithArticle(checked, it_)}`)
    expect(lines[1]).toContain('Officine Esempio Srl: 60 dipendenti')
    expect(lines[1]).toContain('settore NIS: Fabbricazione')
    expect(lines[2]).toBe('Primo filtro indicativo, non un parere legale.')
  })

  it('lists what applies first, each source with its verification and its passage', () => {
    const assessment = assessScope(input, it_)
    expect(byRelevance(assessment.results).map((r) => r.status)).toEqual([
      'in_scope',
      'in_scope',
      'in_scope',
      'out_of_scope',
      'out_of_scope',
      'not_assessed',
    ])
    const text = assessmentToText(assessment, it_)
    expect(text.indexOf('IA nei rapporti di lavoro: Si applica')).toBeLessThan(text.indexOf('CSRD, rendicontazione di sostenibilità: Non si applica'))
    expect(text).toContain('Regolamento macchine (UE) 2023/1230: Si applica (si applica dal 20 gennaio 2027 (art. 54))')
    expect(text).toMatch(/\[1\] Regolamento \(UE\) 2023\/1230 \(regolamento macchine\), art\. 54, secondo comma \(CELEX 32023R1230\) https:\/\/eur-lex\.europa\.eu\/\S+\. Verificata /)
    expect(text).toContain('Testo: «Esso si applica a partire dal 20 gennaio 2027»')
  })
})
