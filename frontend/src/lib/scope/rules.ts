/**
 * Deterministic scope rules for CSRD, CSDDD and AI Act article 50.
 *
 * Every threshold and date is a port of what the repository states:
 *  - public/scope-csrd.html: EMP_T 1000, REV_T 450 (M€), cumulative AND,
 *    margin bands 850-1200 employees and 380-550 M€, listed companies
 *    under the thresholds as a border case, CSDDD 5000 employees and
 *    1,5 bn€, Omnibus I in force 18 March 2026, CELEX 32026L0470.
 *  - public/codex-post-omnibus-2025-2029.pdf: ch. 1.2 (CSRD table, non-EU
 *    threshold 450 M€ EU turnover), ch. 1.4 (CSDDD), ch. 2 (worked
 *    examples 600/120, 1200/380, 1500/620), ch. 5 (calendar).
 *  - public/scope-aiact.html: the four article 50 situations, who bears
 *    each obligation, exceptions, application 2 August 2026 (art. 113),
 *    sanctions art. 99(4) and 99(6), Legge 132/2025, the deferred
 *    high-risk dates, the transitional marking date 2 December 2026.
 *  - prompts/gap_analyst.txt and .planning/decisions/003: CSDDD
 *    transposition 26 July 2028, first compliance 26 July 2029.
 *
 * Anything the sources do not state (balance-sheet total, NIS2, DORA,
 * GDPR, CRA scope thresholds) is deliberately absent.
 */
import type { Source } from '@/lib/sources'
import { eurlexUrl } from '@/lib/sources'
import { formatDateIt } from '@/lib/obligations/dates'
import { formatInt, formatMillionsEur } from './format'
import { SCOPE_SOURCES as S, VERIFIED_ON, withIndex } from './sources'
import type {
  AiActAnswers,
  AiKey,
  AiObligation,
  LegalPassage,
  ScopeAssessment,
  ScopeInput,
  ScopeResult,
} from './types'
import { AI_KEY_FIELD } from './types'

export const CSRD_RULES = {
  employees: 1000,
  turnoverEur: 450_000_000,
  employeesMargin: { min: 850, max: 1200 },
  turnoverMarginEur: { min: 380_000_000, max: 550_000_000 },
  nonEuTurnoverEur: 450_000_000,
} as const

export const CSDDD_RULES = {
  employees: 5000,
  turnoverEur: 1_500_000_000,
} as const

export const SCOPE_DATES = {
  omnibusInForce: '2026-03-18',
  csdddTransposition: '2028-07-26',
  csdddFirstCompliance: '2029-07-26',
  aiActArt4And5: '2025-02-02',
  aiActGpai: '2025-08-02',
  aiActArt50: '2026-08-02',
  aiActLegacyMarking: '2026-12-02',
  aiActHighRiskAnnexIII: '2027-12-02',
  aiActHighRiskAnnexI: '2028-08-02',
} as const

export type CsrdBand = 'in' | 'filo' | 'out'

/** Exact port of classify() in public/scope-csrd.html. */
export function classifyCsrd(employees: number, turnoverEur: number, listed: boolean): CsrdBand {
  const empOver = employees > CSRD_RULES.employees
  const revOver = turnoverEur > CSRD_RULES.turnoverEur
  if (empOver && revOver) return 'in'
  if (empOver || revOver) return 'filo'
  const empMargin = employees >= CSRD_RULES.employeesMargin.min && employees <= CSRD_RULES.employeesMargin.max
  const revMargin = turnoverEur >= CSRD_RULES.turnoverMarginEur.min && turnoverEur <= CSRD_RULES.turnoverMarginEur.max
  if (empMargin || revMargin) return 'filo'
  if (listed) return 'filo'
  return 'out'
}

const CSRD_SOURCES: Source[] = [S.omnibusI, S.csrd, S.dlgs125, S.codex]

function csrdNotes(input: ScopeInput): string[] {
  const notes: string[] = []
  if (input.wave1Reporter) {
    notes.push(
      'Hai indicato una rendicontazione già in corso (Wave 1, FY2024): l’Omnibus I prevede un’esenzione transitoria per gli esercizi 2025 e 2026, dopo la quale si riapplicano le nuove soglie sull’esercizio rilevante.',
    )
  }
  if (input.groupRole === 'parent') {
    notes.push(
      'Capogruppo: i valori vanno letti sul bilancio consolidato; per i gruppi la base è l’art. 29-bis della Direttiva 2013/34/UE.',
    )
  }
  if (input.groupRole === 'subsidiary') {
    notes.push(
      'Società controllata: l’ambito può dipendere dal perimetro di consolidamento e dalla rendicontazione della capogruppo. Serve una verifica puntuale sul gruppo.',
    )
  }
  return notes
}

function assessCsrd(input: ScopeInput): ScopeResult {
  const base = {
    framework: 'CSRD' as const,
    sources: withIndex(CSRD_SOURCES),
    passages: [] as LegalPassage[],
    verifiedOn: VERIFIED_ON,
  }
  const fromLabel = `Soglie in vigore dal ${formatDateIt(SCOPE_DATES.omnibusInForce)} (Omnibus I)`

  if (input.nonEu) {
    if (input.euTurnoverEur == null) {
      return {
        ...base,
        status: 'not_assessed',
        headline: 'Indica i ricavi netti realizzati nell’Unione per valutare la CSRD come impresa di un Paese terzo.',
        reasons: [],
        notes: [],
      }
    }
    const over = input.euTurnoverEur > CSRD_RULES.nonEuTurnoverEur
    if (over) {
      return {
        ...base,
        status: 'conditional',
        headline: 'Può applicarsi la rendicontazione prevista per le imprese di Paesi terzi.',
        from: SCOPE_DATES.omnibusInForce,
        fromLabel,
        reasons: [
          `Ricavi netti nell’Unione: ${formatMillionsEur(input.euTurnoverEur)}, oltre la soglia di ${formatMillionsEur(CSRD_RULES.nonEuTurnoverEur)} indicata dal Codex per le imprese extra-UE.`,
          'Il Codex (cap. 1.2) lega l’obbligo anche alla presenza di una sussidiaria o succursale nell’Unione sopra 200 milioni di euro: la verifica richiede il bilancio consolidato del gruppo e i ricavi per Stato membro (cap. 2.4, caso 2).',
        ],
        notes: csrdNotes(input),
      }
    }
    return {
      ...base,
      status: 'out_of_scope',
      headline: 'Sotto la soglia di ricavi UE per le imprese di Paesi terzi.',
      reasons: [
        `Ricavi netti nell’Unione: ${formatMillionsEur(input.euTurnoverEur)}, sotto la soglia di ${formatMillionsEur(CSRD_RULES.nonEuTurnoverEur)} (Codex, cap. 2.1).`,
        'Una società di diritto italiano controllata dal gruppo può comunque rientrare come sussidiaria UE: in quel caso valuta la controllata con le soglie UE.',
      ],
      notes: csrdNotes(input),
    }
  }

  if (input.employees == null || input.turnoverEur == null) {
    return {
      ...base,
      status: 'not_assessed',
      headline: 'Indica il numero medio di dipendenti e i ricavi netti annui per valutare la CSRD.',
      reasons: [],
      notes: [],
    }
  }

  const employees = input.employees
  const turnover = input.turnoverEur
  const empOver = employees > CSRD_RULES.employees
  const revOver = turnover > CSRD_RULES.turnoverEur
  const band = classifyCsrd(employees, turnover, input.listedEu)
  const axis = [
    `Dipendenti: ${formatInt(employees)} (${empOver ? 'oltre' : 'non oltre'} ${formatInt(CSRD_RULES.employees)}).`,
    `Ricavi netti: ${formatMillionsEur(turnover)} (${revOver ? 'oltre' : 'non oltre'} ${formatMillionsEur(CSRD_RULES.turnoverEur)}).`,
  ]

  if (band === 'in') {
    return {
      ...base,
      status: 'in_scope',
      headline: 'L’impresa è quasi certamente in ambito di rendicontazione CSRD.',
      from: SCOPE_DATES.omnibusInForce,
      fromLabel,
      reasons: [
        'Superi entrambe le soglie cumulative post-Omnibus: più di 1.000 dipendenti e oltre 450 milioni di euro di ricavi netti. Salvo esenzioni specifiche, ricadi nell’obbligo di rendicontazione di sostenibilità secondo gli ESRS.',
        ...axis,
      ],
      notes: [
        'Verifica le esenzioni: reporter Wave 1 (esenzione transitoria FY2025-2026) e perimetri di gruppo con holding possono cambiare il quadro.',
        'Doppia materialità ed ESRS Set 1 (ridotto di circa il 61% dei datapoint) restano il cuore del lavoro: la riduzione non semplifica l’assessment.',
        ...csrdNotes(input),
      ],
    }
  }

  if (band === 'filo') {
    let reason: string
    const nearMargin =
      (employees >= CSRD_RULES.employeesMargin.min && employees <= CSRD_RULES.employeesMargin.max) ||
      (turnover >= CSRD_RULES.turnoverMarginEur.min && turnover <= CSRD_RULES.turnoverMarginEur.max)
    if (empOver && !revOver) {
      reason =
        'Superi la soglia dei dipendenti ma non quella dei ricavi: poiché la regola è cumulativa, oggi sei fuori dall’obbligo, ma basta una crescita dei ricavi o un cambio di perimetro per entrarci.'
    } else if (revOver && !empOver) {
      reason =
        'Superi la soglia dei ricavi ma non quella dei dipendenti: poiché la regola è cumulativa, oggi sei fuori dall’obbligo, ma un’assunzione netta o un consolidamento può farti entrare.'
    } else if (input.listedEu && !nearMargin) {
      reason =
        'Come società quotata sotto le nuove soglie dimensionali sei in linea di principio esclusa, ma la posizione di una quotata va confermata caso per caso (obblighi da mercato regolamentato, perimetro di gruppo).'
    } else {
      reason =
        'Oggi sei fuori dall’obbligo, ma sei a ridosso di una soglia: piccole variazioni di organico, ricavi o perimetro di consolidamento ti fanno oscillare dentro e fuori da un esercizio all’altro.'
    }
    return {
      ...base,
      status: 'conditional',
      headline: 'Oggi fuori dall’obbligo CSRD, ma sul filo della soglia.',
      from: SCOPE_DATES.omnibusInForce,
      fromLabel,
      reasons: [reason, ...axis, 'È il caso in cui una verifica puntuale (e una scelta tra obbligo, adozione volontaria e VSME) vale di più.'],
      notes: [
        'Perimetro variabile: l’ambito si misura a fine esercizio, ma i dati ESG vanno raccolti su tutto l’anno. Con M&A o riassetti in corso l’analisi diventa multi-scenario.',
        'Pressione di filiera: anche fuori dall’obbligo, i clienti in ambito CSRD o CSDDD chiederanno disclosure (VSME) come fornitore.',
        ...csrdNotes(input),
      ],
    }
  }

  return {
    ...base,
    status: 'out_of_scope',
    headline: 'Probabilmente fuori dall’ambito di rendicontazione CSRD obbligatoria.',
    reasons: [
      'Non superi le soglie cumulative post-Omnibus (1.000 dipendenti e 450 milioni di euro di ricavi netti). L’obbligo diretto non scatta, ma fuori dalla CSRD non significa fuori da tutto.',
      ...axis,
    ],
    notes: [
      'Pressione di filiera (VSME): se sei fornitore di un gruppo in ambito, riceverai richieste di disclosure di sostenibilità lungo la catena.',
      'Tassonomia indiretta: se hai finanziamento bancario, la banca (per il proprio GAR) può chiederti dati Taxonomy-eligible.',
      'CSDDD di filiera: i grandi gruppi obbligati alla due diligence trasferiscono requisiti ai fornitori, ben sotto le loro soglie dirette.',
      ...csrdNotes(input),
    ],
  }
}

const CSDDD_SOURCES: Source[] = [S.csddd, S.omnibusI, S.codex]

function assessCsddd(input: ScopeInput): ScopeResult {
  const base = {
    framework: 'CSDDD' as const,
    sources: withIndex(CSDDD_SOURCES),
    passages: [] as LegalPassage[],
    verifiedOn: VERIFIED_ON,
  }

  if (input.nonEu) {
    return {
      ...base,
      status: 'not_assessed',
      headline: 'Per le imprese di Paesi terzi le fonti disponibili non riportano le soglie CSDDD: non valutato.',
      reasons: [],
      notes: [],
    }
  }
  if (input.employees == null || input.turnoverEur == null) {
    return {
      ...base,
      status: 'not_assessed',
      headline: 'Indica dipendenti e ricavi netti per valutare la CSDDD.',
      reasons: [],
      notes: [],
    }
  }

  const empOver = input.employees > CSDDD_RULES.employees
  const revOver = input.turnoverEur > CSDDD_RULES.turnoverEur
  const axis = [
    `Dipendenti: ${formatInt(input.employees)} (${empOver ? 'oltre' : 'non oltre'} ${formatInt(CSDDD_RULES.employees)}).`,
    `Ricavi netti: ${formatMillionsEur(input.turnoverEur)} (${revOver ? 'oltre' : 'non oltre'} ${formatMillionsEur(CSDDD_RULES.turnoverEur)}).`,
  ]
  const calendar = `Recepimento negli Stati membri entro il ${formatDateIt(SCOPE_DATES.csdddTransposition)}, prima applicazione dal ${formatDateIt(SCOPE_DATES.csdddFirstCompliance)} (Direttiva (UE) 2026/470).`

  if (empOver && revOver) {
    return {
      ...base,
      status: 'in_scope',
      headline: 'Superi anche le soglie dirette del dovere di diligenza (CSDDD).',
      from: SCOPE_DATES.csdddFirstCompliance,
      fromLabel: `Prima applicazione dal ${formatDateIt(SCOPE_DATES.csdddFirstCompliance)}`,
      reasons: [
        'Superi entrambe le soglie cumulative post-Omnibus: più di 5.000 dipendenti e oltre 1,5 miliardi di euro di ricavi netti.',
        ...axis,
        calendar,
      ],
      notes: [
        'L’Omnibus I ha rimosso l’obbligo del piano di transizione climatica e il regime armonizzato di responsabilità civile, e ha sostituito la mappatura completa della catena del valore con un esercizio generale di scoping (Codex, cap. 1.4).',
        'Sanzioni: tetto massimo al 3% dei ricavi netti mondiali (Codex, cap. 1.4).',
      ],
    }
  }

  const which =
    empOver || revOver
      ? 'Superi una sola delle due soglie cumulative: l’obbligo diretto oggi non scatta.'
      : 'Non superi le soglie cumulative post-Omnibus (5.000 dipendenti e 1,5 miliardi di euro): l’obbligo diretto non scatta.'
  return {
    ...base,
    status: 'out_of_scope',
    headline: 'Fuori dalle soglie dirette del dovere di diligenza (CSDDD).',
    reasons: [which, ...axis, calendar],
    notes: [
      'CSDDD di filiera: i grandi gruppi obbligati trasferiscono requisiti ai fornitori, ben sotto le loro soglie dirette. Le richieste di disclosure in catena arrivano prima della scadenza di legge.',
    ],
  }
}

/** The article 50 passage as the landing page cites it from the official Italian text. */
const ART_50_1_PASSAGE: LegalPassage = {
  before:
    'I fornitori garantiscono che i sistemi di IA destinati a interagire direttamente con le persone fisiche sono progettati e sviluppati in modo tale che le persone fisiche interessate',
  quote: 'siano informate del fatto che stanno interagendo con un sistema di IA',
  after:
    'a meno che ciò non risulti evidente dal punto di vista di una persona fisica ragionevolmente informata, attenta e avveduta',
  act: 'Regolamento (UE) 2024/1689',
  article: 'art. 50, par. 1',
  celex: '32024R1689',
  url: eurlexUrl('32024R1689'),
}

/** Port of OBS in public/scope-aiact.html. */
export const AI_OBLIGATIONS: Record<AiKey, AiObligation> = {
  chat: {
    key: 'chat',
    who: 'provider',
    whoLabel: 'Obbligo del fornitore',
    title: 'Chatbot e assistenti: la persona deve sapere che sta parlando con un’IA',
    requirement:
      'I sistemi di IA destinati a interagire direttamente con le persone vanno progettati e sviluppati in modo che la persona sia informata di stare interagendo con un’IA, a meno che ciò non sia evidente per una persona ragionevolmente informata e attenta.',
    exception:
      'Eccezione: sistemi autorizzati per legge per finalità di contrasto, a determinate condizioni. Se il chatbot lo comprate da terzi, l’obbligo di progettazione è del fornitore, ma verificare che lo rispetti conviene a voi.',
    article: 'art. 50, par. 1',
    source: S.aiAct50_1,
  },
  gen: {
    key: 'gen',
    who: 'provider',
    whoLabel: 'Obbligo del fornitore',
    title: 'Contenuti generati: marcatura leggibile dalle macchine',
    requirement:
      'I fornitori di sistemi che generano contenuti sintetici (audio, immagini, video o testo) devono garantire che gli output siano marcati in un formato leggibile dalle macchine e rilevabili come generati o manipolati artificialmente; le soluzioni tecniche devono essere efficaci, interoperabili, robuste e affidabili per quanto tecnicamente possibile.',
    exception:
      'Eccezioni: funzioni di assistenza all’editing standard o che non alterano sostanzialmente i dati di input, e ambiti autorizzati per legge. Transitorio: per i sistemi generativi già sul mercato prima del 2 agosto 2026 la marcatura si applica dal 2 dicembre 2026; per i sistemi nuovi vale il 2 agosto 2026. Un Codice di buone pratiche UE sulla trasparenza dei contenuti IA (10 giugno 2026, adesione volontaria) supporta l’attuazione.',
    article: 'art. 50, par. 2',
    source: S.aiAct50_2,
  },
  emo: {
    key: 'emo',
    who: 'deployer',
    whoLabel: 'Obbligo dell’utilizzatore',
    title: 'Riconoscimento delle emozioni e categorizzazione biometrica: informare le persone esposte',
    requirement:
      'Chi utilizza un sistema di riconoscimento delle emozioni o di categorizzazione biometrica deve informare le persone fisiche che vi sono esposte sul funzionamento del sistema, e trattare i dati personali nel rispetto del GDPR.',
    exception:
      'Attenzione ai divieti già in vigore (art. 5, dal 2 febbraio 2025): per esempio il riconoscimento delle emozioni sul luogo di lavoro e negli istituti di istruzione è vietato, salvo motivi medici o di sicurezza.',
    article: 'art. 50, par. 3',
    source: S.aiAct50_3,
  },
  deep: {
    key: 'deep',
    who: 'deployer',
    whoLabel: 'Obbligo dell’utilizzatore',
    title: 'Deepfake e testi IA pubblicati: dichiararne l’origine',
    requirement:
      'Chi utilizza un sistema che genera o manipola immagini, audio o video costituenti deepfake deve rendere noto che il contenuto è stato generato o manipolato artificialmente. Lo stesso vale per i testi generati dall’IA pubblicati per informare il pubblico su questioni di interesse pubblico.',
    exception:
      'Eccezioni: per opere manifestamente artistiche, creative o satiriche la disclosure va data in modo appropriato senza pregiudicare l’opera; per i testi, l’obbligo non si applica se c’è revisione umana o controllo editoriale e una persona fisica o giuridica se ne assume la responsabilità editoriale.',
    article: 'art. 50, par. 4',
    source: S.aiAct50_4,
  },
}

export const AI_KEYS: AiKey[] = ['chat', 'gen', 'emo', 'deep']

export function selectedAiKeys(ai: AiActAnswers): AiKey[] {
  return AI_KEYS.filter((k) => ai[AI_KEY_FIELD[k]])
}

function assessAiAct(input: ScopeInput): ScopeResult {
  const base = {
    framework: 'AI_ACT' as const,
    verifiedOn: VERIFIED_ON,
  }

  if (input.ai == null) {
    return {
      ...base,
      status: 'not_assessed',
      headline: 'Rispondi alle quattro domande sull’IA per valutare gli obblighi di trasparenza dell’art. 50.',
      reasons: [],
      notes: [],
      sources: withIndex([S.aiAct50_1, S.aiAct113]),
      passages: [],
    }
  }

  const keys = selectedAiKeys(input.ai)

  if (keys.length === 0) {
    return {
      ...base,
      status: 'out_of_scope',
      headline: 'Dalle risposte, gli obblighi di trasparenza dell’art. 50 non vi toccano direttamente.',
      reasons: [
        'Nessuna delle quattro situazioni dell’art. 50 risulta applicabile. Fuori dall’art. 50 non significa fuori dall’AI Act.',
      ],
      notes: [
        `Alfabetizzazione in materia di IA (art. 4): applicabile dal ${formatDateIt(SCOPE_DATES.aiActArt4And5)} a chiunque fornisca o utilizzi sistemi di IA: il personale che usa l’IA deve avere un livello adeguato di competenza.`,
        `Pratiche vietate (art. 5): in vigore dal ${formatDateIt(SCOPE_DATES.aiActArt4And5)} (per esempio manipolazione dannosa, social scoring, riconoscimento delle emozioni sul lavoro).`,
        `Modelli di IA per finalità generali: se fornite modelli GPAI, gli obblighi del Capo V si applicano dal ${formatDateIt(SCOPE_DATES.aiActGpai)}, con poteri di enforcement dal 2026.`,
        `Alto rischio: rinviato, non cancellato. La disciplina si applica dal ${formatDateIt(SCOPE_DATES.aiActHighRiskAnnexIII)} per i sistemi stand-alone (allegato III) e dal ${formatDateIt(SCOPE_DATES.aiActHighRiskAnnexI)} per l’IA integrata in prodotti regolamentati (allegato I); la preparazione richiede mesi.`,
      ],
      sources: withIndex([S.aiAct4, S.aiAct5, S.aiActGpai, S.aiActHighRisk, S.aiAct113]),
      passages: [],
    }
  }

  const obligations = keys.map((k) => AI_OBLIGATIONS[k])
  const sources = withIndex([
    ...obligations.map((o) => o.source),
    S.aiAct50_5,
    S.aiAct113,
    S.aiAct99,
    S.legge132,
  ])

  return {
    ...base,
    status: 'in_scope',
    headline: `Dal ${formatDateIt(SCOPE_DATES.aiActArt50)} l’art. 50 tocca le situazioni che hai indicato.`,
    from: SCOPE_DATES.aiActArt50,
    fromLabel: `Applicazione dal ${formatDateIt(SCOPE_DATES.aiActArt50)} (art. 113)`,
    reasons: [
      ...obligations.map((o) => `${o.whoLabel}: ${o.title} (${o.article}).`),
      'Attenzione a chi è il destinatario: alcuni obblighi gravano su chi fornisce il sistema, altri su chi lo utilizza. Se il vostro ruolo è solo di utilizzatore, gli obblighi del fornitore gravano sul vostro fornitore, e viceversa.',
      'Le informazioni vanno date in modo chiaro e riconoscibile, al più tardi alla prima interazione o esposizione (art. 50, par. 5).',
    ],
    notes: [
      'Sanzioni: fino a 15 milioni di euro o al 3% del fatturato mondiale annuo, se superiore; per PMI e start-up il minore dei due importi (art. 99, par. 4 e par. 6).',
      'In Italia la Legge 132/2025 designa ACN (vigilanza e sanzioni) e AgID come autorità nazionali per l’AI Act.',
      `Cosa non scatta il 2 agosto 2026: la disciplina dei sistemi ad alto rischio (allegato III), rinviata al ${formatDateIt(SCOPE_DATES.aiActHighRiskAnnexIII)} dal pacchetto Omnibus digitale.`,
    ],
    sources,
    passages: keys.includes('chat') ? [ART_50_1_PASSAGE] : [],
    obligations,
  }
}

export function assessScope(input: ScopeInput): ScopeAssessment {
  return {
    input,
    results: [assessCsrd(input), assessCsddd(input), assessAiAct(input)],
    verifiedOn: VERIFIED_ON,
  }
}
