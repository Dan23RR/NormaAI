/**
 * Dated obligations and milestones for the Monitoraggio calendar.
 *
 * Curated by hand. Every date comes from a file of this repository and the
 * entry says which one (`sourceNote`). Dates the sources give only by month
 * or quarter keep that precision; entries the sources present as expected
 * rather than fixed carry `confirmed: false` and the interface says so.
 * No automatic EUR-Lex watcher feeds this list yet.
 */
import type { Source } from '@/lib/sources'
import { SCOPE_SOURCES as S, VERIFIED_ON } from '@/lib/scope/sources'
import { addDays, parseIsoDate, startOfDay, toIsoDate, type DatePrecision } from './dates'

export interface Obligation {
  id: string
  /** ISO date. Month precision uses day 01; quarter precision uses the first day of the quarter. */
  date: string
  precision: DatePrecision
  /** Key of FRAMEWORK_META (CSRD, CSDDD, AI_ACT, CRA, NIS2, DORA, ...). */
  framework: string
  title: string
  /** Who the entry applies to. */
  who: string
  /** What to do. */
  what: string
  source: Source
  /** Where in the repository the date was read. */
  sourceNote: string
  /** False when the sources present the date as expected, not fixed. */
  confirmed: boolean
  verifiedOn: string
}

type Draft = Omit<Obligation, 'verifiedOn' | 'confirmed' | 'precision'> & {
  precision?: DatePrecision
  confirmed?: boolean
}

function entry(d: Draft): Obligation {
  return { precision: 'day', confirmed: true, verifiedOn: VERIFIED_ON, ...d }
}

export const OBLIGATIONS: Obligation[] = [
  entry({
    id: 'nis2-application',
    date: '2024-10-18',
    framework: 'NIS2',
    title: 'NIS2 in applicazione',
    who: 'Soggetti essenziali e importanti (in Italia: D.Lgs. 138/2024)',
    what: 'Misure di sicurezza e notifica degli incidenti.',
    source: S.nis2,
    sourceNote: 'Codex, cap. 5.1 e note (CELEX 32022L2555); landing, tabella Fonti',
  }),
  entry({
    id: 'dora-application',
    date: '2025-01-17',
    framework: 'DORA',
    title: 'DORA in applicazione',
    who: 'Settore finanziario e fornitori ICT terzi',
    what: 'Resilienza operativa digitale e gestione del rischio ICT.',
    source: S.dora,
    sourceNote: 'Codex, cap. 5.1 e note (CELEX 32022R2554); landing, tabella Fonti',
  }),
  entry({
    id: 'aiact-art4-art5',
    date: '2025-02-02',
    framework: 'AI_ACT',
    title: 'AI Act: alfabetizzazione (art. 4) e pratiche vietate (art. 5)',
    who: 'Chiunque fornisca o utilizzi sistemi di IA',
    what: 'Competenza adeguata del personale che usa l’IA; divieti già in vigore, per esempio manipolazione dannosa, social scoring, riconoscimento delle emozioni sul luogo di lavoro.',
    source: S.aiAct5,
    sourceNote: 'public/scope-aiact.html, note del verdetto',
  }),
  entry({
    id: 'aiact-gpai',
    date: '2025-08-02',
    framework: 'AI_ACT',
    title: 'AI Act: obblighi per i modelli di IA per finalità generali (Capo V)',
    who: 'Fornitori di modelli GPAI',
    what: 'Obblighi del Capo V; poteri di enforcement dal 2026.',
    source: S.aiActGpai,
    sourceNote: 'public/scope-aiact.html, note del verdetto',
  }),
  entry({
    id: 'omnibus-published',
    date: '2026-02-26',
    framework: 'CSRD',
    title: 'Omnibus I pubblicato in Gazzetta ufficiale dell’Unione',
    who: 'Imprese in ambito CSRD e CSDDD',
    what: 'Direttiva (UE) 2026/470: nuove soglie CSRD (1.000 dipendenti e 450 milioni di euro, cumulative) e nuovo calendario CSDDD.',
    source: S.omnibusI,
    sourceNote: 'README.md, Regulatory Context; .planning/decisions/003',
  }),
  entry({
    id: 'omnibus-in-force',
    date: '2026-03-18',
    framework: 'CSRD',
    title: 'Omnibus I in vigore: nuove soglie CSRD',
    who: 'Imprese sopra 1.000 dipendenti e 450 milioni di euro di ricavi netti',
    what: 'Verificare l’ambito con le soglie cumulative; le PMI quotate escono dal perimetro; esenzione transitoria FY2025-2026 per i reporter Wave 1.',
    source: S.omnibusI,
    sourceNote: 'public/scope-csrd.html; prompts/gap_analyst.txt riga 45; README.md',
  }),
  entry({
    id: 'aiact-code-of-practice',
    date: '2026-06-10',
    framework: 'AI_ACT',
    title: 'Codice di buone pratiche UE sulla trasparenza dei contenuti IA',
    who: 'Fornitori di sistemi generativi (adesione volontaria)',
    what: 'Riferimento per attuare la marcatura dei contenuti dell’art. 50, par. 2.',
    source: S.aiAct50_2,
    sourceNote: 'public/scope-aiact.html, obbligo "gen"',
  }),
  entry({
    id: 'aiact-art50',
    date: '2026-08-02',
    framework: 'AI_ACT',
    title: 'AI Act: obblighi di trasparenza dell’art. 50',
    who: 'Fornitori e utilizzatori di chatbot, sistemi generativi, riconoscimento delle emozioni, deepfake',
    what: 'Informare le persone che interagiscono con un’IA, marcare i contenuti sintetici, dichiarare i deepfake (art. 50, par. 1-4); applicazione dall’art. 113.',
    source: S.aiAct113,
    sourceNote: 'public/scope-aiact.html; src/app/page.tsx (esempio di risposta); Codex, cap. 5.2',
  }),
  entry({
    id: 'cra-reporting',
    date: '2026-09-11',
    framework: 'CRA',
    title: 'CRA: segnalazione di vulnerabilità sfruttate e incidenti gravi',
    who: 'Fabbricanti di prodotti con elementi digitali, anche già sul mercato',
    what: 'Allerta precoce entro 24 ore e notifica entro 72 ore tramite la piattaforma ENISA (art. 14).',
    source: S.cra,
    sourceNote: 'prompts/gap_analyst.txt riga 47; .planning/decisions/004',
  }),
  entry({
    id: 'aiact-legacy-marking',
    date: '2026-12-02',
    framework: 'AI_ACT',
    title: 'AI Act: marcatura dei contenuti per i sistemi generativi già sul mercato',
    who: 'Fornitori di sistemi generativi immessi sul mercato prima del 2 agosto 2026',
    what: 'Output marcati in formato leggibile dalle macchine (art. 50, par. 2); transitorio del pacchetto Omnibus digitale.',
    source: S.aiAct50_2,
    sourceNote: 'public/scope-aiact.html, obbligo "gen"',
  }),
  entry({
    id: 'csrd-prepare-fy2027',
    date: '2026-12-31',
    framework: 'CSRD',
    title: 'CSRD: preparazione dell’esercizio 2027 per i gruppi ancora in ambito',
    who: 'Gruppi oltre 1.000 dipendenti e 450 milioni di euro',
    what: 'Impostare raccolta dati ESG e doppia materialità per l’esercizio FY2027.',
    source: S.codex,
    sourceNote: 'Codex, cap. 5.2 (2026, Q3)',
  }),
  entry({
    id: 'csrd-first-post-omnibus',
    date: '2027-01-01',
    precision: 'quarter',
    framework: 'CSRD',
    title: 'CSRD: prima rendicontazione post-Omnibus sul nuovo perimetro',
    who: 'Imprese in ambito con le nuove soglie',
    what: 'Dichiarazione di sostenibilità secondo gli ESRS Set 1 rivisti. Il Codex indica l’esercizio 2026 nel calendario e l’esercizio 2027 nella tabella: da confermare sul testo consolidato.',
    source: S.codex,
    sourceNote: 'Codex, cap. 5.1 e 5.2 (2027, Q1)',
    confirmed: false,
  }),
  entry({
    id: 'csrd-csddd-review-clause',
    date: '2027-04-01',
    precision: 'quarter',
    framework: 'CSRD',
    title: 'Clausola di revisione CSRD e CSDDD: possibile estensione dell’ambito',
    who: 'Commissione europea; imprese appena fuori dalle soglie',
    what: 'Avvio della revisione prevista dall’Omnibus I; un riallargamento del perimetro è possibile.',
    source: S.codex,
    sourceNote: 'Codex, cap. 1.2 e 5.2 (2027, Q2)',
    confirmed: false,
  }),
  entry({
    id: 'csddd-guidelines',
    date: '2027-07-01',
    precision: 'month',
    framework: 'CSDDD',
    title: 'Linee guida della Commissione sulla CSDDD',
    who: 'Imprese in ambito CSDDD e loro fornitori',
    what: 'Attese per luglio 2027; data non fissata da un atto.',
    source: S.csddd,
    sourceNote: '.planning/decisions/003 (verifica 2026-06-11)',
    confirmed: false,
  }),
  entry({
    id: 'aiact-high-risk-annex-iii',
    date: '2027-12-02',
    framework: 'AI_ACT',
    title: 'AI Act: sistemi ad alto rischio stand-alone (allegato III)',
    who: 'Fornitori e utilizzatori di sistemi ad alto rischio',
    what: 'Valutazione di conformità e sistema di gestione della qualità; data rinviata dal pacchetto Omnibus digitale (via libera del Consiglio UE, 29 giugno 2026). Il Codex di aprile 2026 riportava ancora il 2 agosto 2027.',
    source: S.aiActHighRisk,
    sourceNote: 'public/scope-aiact.html (quadro aggiornato al 12 luglio 2026)',
  }),
  entry({
    id: 'cra-full-application',
    date: '2027-12-11',
    framework: 'CRA',
    title: 'CRA: piena applicazione',
    who: 'Fabbricanti, importatori e distributori di prodotti con elementi digitali',
    what: 'Requisiti essenziali di cybersicurezza e valutazione di conformità; categorie di prodotti nel Regolamento di esecuzione (UE) 2025/2392.',
    source: S.cra,
    sourceNote: 'prompts/gap_analyst.txt riga 47; .planning/decisions/004',
  }),
  entry({
    id: 'csrd-wave1-fy2027',
    date: '2028-04-01',
    precision: 'quarter',
    framework: 'CSRD',
    title: 'CSRD: prima rendicontazione FY2027 per i reporter Wave 1',
    who: 'Imprese già in rendicontazione dal FY2024, dopo l’esenzione transitoria',
    what: 'Rendicontazione sull’esercizio 2027 con le soglie post-Omnibus.',
    source: S.codex,
    sourceNote: 'Codex, cap. 5.2 (2028, Q2)',
  }),
  entry({
    id: 'csddd-transposition',
    date: '2028-07-26',
    framework: 'CSDDD',
    title: 'CSDDD: termine di recepimento negli Stati membri',
    who: 'Stati membri; le imprese in ambito preparano il dovere di diligenza',
    what: 'Recepimento nazionale della direttiva come modificata dall’Omnibus I.',
    source: S.csddd,
    sourceNote: 'public/scope-csrd.html; Codex, cap. 1.4 e 5; prompts/gap_analyst.txt riga 46; .planning/decisions/003; landing, tabella Fonti',
  }),
  entry({
    id: 'aiact-high-risk-annex-i',
    date: '2028-08-02',
    framework: 'AI_ACT',
    title: 'AI Act: alto rischio per l’IA integrata in prodotti regolamentati (allegato I)',
    who: 'Fabbricanti di prodotti regolamentati con componenti di IA',
    what: 'Applicazione della disciplina ad alto rischio ai prodotti dell’allegato I.',
    source: S.aiActHighRisk,
    sourceNote: 'public/scope-aiact.html (quadro aggiornato al 12 luglio 2026)',
  }),
  entry({
    id: 'csddd-first-compliance',
    date: '2029-07-26',
    framework: 'CSDDD',
    title: 'CSDDD: prima applicazione',
    who: 'Imprese con più di 5.000 dipendenti e oltre 1,5 miliardi di euro di ricavi netti',
    what: 'Dovere di diligenza sulla catena di attività; sanzioni fino al 3% dei ricavi netti mondiali. Il Codex indica "luglio 2029"; il giorno 26 viene dal prompt e dall’ADR-003.',
    source: S.csddd,
    sourceNote: 'prompts/gap_analyst.txt riga 46; .planning/decisions/003; Codex, cap. 2.2 e 5.2',
  }),
]

function byDate(a: Obligation, b: Obligation): number {
  return a.date < b.date ? -1 : a.date > b.date ? 1 : a.id.localeCompare(b.id)
}

/** Entries dated within [from, from + days], ascending. */
export function upcoming(from: Date, days: number, list: Obligation[] = OBLIGATIONS): Obligation[] {
  const start = toIsoDate(startOfDay(from))
  const end = toIsoDate(addDays(startOfDay(from), days))
  return list.filter((o) => o.date >= start && o.date <= end).sort(byDate)
}

/** Entries dated before `from`, most recent first. */
export function past(from: Date, list: Obligation[] = OBLIGATIONS): Obligation[] {
  const start = toIsoDate(startOfDay(from))
  return list.filter((o) => o.date < start).sort((a, b) => byDate(b, a))
}

export interface MonthGroup {
  /** 'YYYY-MM' */
  key: string
  /** ISO date of the first day, for formatting the heading. */
  firstDay: string
  items: Obligation[]
}

export function groupByMonth(list: Obligation[]): MonthGroup[] {
  const groups = new Map<string, MonthGroup>()
  for (const o of [...list].sort(byDate)) {
    const key = o.date.slice(0, 7)
    const group = groups.get(key) ?? { key, firstDay: `${key}-01`, items: [] }
    group.items.push(o)
    groups.set(key, group)
  }
  return Array.from(groups.values())
}

export function isPast(o: Obligation, today: Date): boolean {
  return parseIsoDate(o.date) < startOfDay(today)
}
