/**
 * Demo answers of "Analizza una novità", Italian and English. The demo does
 * not read the change that was pasted: it recognises which act the text
 * names and shows how the applicability of that act to the chosen profile is
 * read, with the dates in force. Every answer says so. Thresholds, dates and
 * article numbers were read on the official texts on 2026-11-11 (EUR-Lex and
 * Normattiva; see scope.ts for the thresholds).
 */
import type { Language } from '@/i18n/config'
import type { MonitorResponse } from '../types'
import { demoLanguage } from './language'
import {
  CSRD_EMPLOYEES,
  companyName,
  csdddScope,
  csrdScope,
  describeSize,
  doraScope,
  nis2Scope,
} from './scope'
import type { DemoProfile } from './types'

type Topic = 'csrd' | 'csddd' | 'taxonomy' | 'ai_act' | 'gdpr' | 'nis2' | 'dora' | 'cra'

type Texts<T> = Record<Language, T>

interface Scenario {
  applicability: MonitorResponse['applicability']
  urgency: MonitorResponse['urgency']
  reason: Texts<string>
  impact: Texts<string>
  actions: Texts<string[]>
  deadline: string
  deadlineConfirmed: boolean
  cross: Texts<string[]>
  citations: Texts<string[]>
  confidence: number
  expertReview: boolean
}

/** Said at the end of every answer: what the demo did and did not do. */
const DEMO_NOTE: Texts<string> = {
  it: "Esempio della demo: descrive l'ambito normativo riconosciuto nel testo, non la singola novità incollata.",
  en: 'Demo example: it describes the regulatory area recognised in the text, not the specific change that was pasted.',
}

interface Context {
  profile: DemoProfile | undefined
  /** "Alfa S.r.l. (con 85 dipendenti e ...)" or the bare name when the profile has no size. */
  who: Texts<string>
}

function contextOf(profile: DemoProfile | undefined): Context {
  const named = (language: Language) => {
    const name = companyName(profile, language)
    const size = describeSize(profile, language)
    return size ? `${name} (${size})` : name
  }
  return { profile, who: { it: named('it'), en: named('en') } }
}

// ─── CSRD ───────────────────────────────────────────────────

function csrd({ profile, who }: Context): Scenario {
  const scope = csrdScope(profile)
  const citations: Texts<string[]> = {
    it: ['Direttiva 2013/34/UE, art. 19 bis, par. 1 e 3', 'Direttiva (UE) 2022/2464, art. 5, par. 2', 'Direttiva (UE) 2026/470, art. 5'],
    en: ['Directive 2013/34/EU, Art. 19a(1) and (3)', 'Directive (EU) 2022/2464, Art. 5(2)', 'Directive (EU) 2026/470, Art. 5'],
  }
  const cross: Texts<string[]> = {
    it: [
      "Tassonomia: l'informativa dell'articolo 8 del Regolamento (UE) 2020/852 riguarda le stesse imprese",
      'CSDDD: soglie diverse (più di 5.000 dipendenti e fatturato netto mondiale oltre 1,5 miliardi di euro), regole applicabili dal 26 luglio 2029',
    ],
    en: [
      'Taxonomy: the disclosure of Article 8 of Regulation (EU) 2020/852 concerns the same undertakings',
      'CSDDD: different thresholds (more than 5,000 employees and a net worldwide turnover above EUR 1.5 billion), rules applicable from 26 July 2029',
    ],
  }

  if (scope === 'above') {
    return {
      applicability: 'YES',
      urgency: 'HIGH',
      reason: {
        it: `${who.it} supera entrambe le soglie della rendicontazione di sostenibilità: l'obbligo resta.`,
        en: `${who.en} exceeds both thresholds for sustainability reporting: the obligation remains.`,
      },
      impact: {
        it: "La Direttiva (UE) 2026/470, in vigore dal 18 marzo 2026, limita l'obbligo alle imprese con più di 1.000 dipendenti e più di 450 milioni di euro di ricavi netti, per gli esercizi che iniziano dal 1° gennaio 2027. Per chi resta in ambito cambiano anche i principi di rendicontazione (Regolamento delegato (UE) 2026/1563, in vigore dal 10 novembre 2026) e ciò che si può chiedere ai fornitori fino a 1.000 dipendenti.",
        en: 'Directive (EU) 2026/470, in force since 18 March 2026, limits the obligation to undertakings with more than 1,000 employees and a net turnover above EUR 450 million, for financial years starting on or after 1 January 2027. For those that stay in scope the reporting standards also change (Delegated Regulation (EU) 2026/1563, in force since 10 November 2026), and so does what can be asked of suppliers with up to 1,000 employees.',
      },
      actions: {
        it: [
          "Confermare le due soglie sull'ultimo bilancio approvato",
          "Scegliere quale versione degli ESRS applicare per l'esercizio 2026",
          'Rivedere i questionari ai fornitori entro il limite dei principi volontari',
          'Seguire il recepimento italiano delle modifiche, dovuto entro il 19 marzo 2027',
        ],
        en: [
          'Confirm both thresholds on the last approved financial statements',
          'Choose which version of the ESRS to apply for financial year 2026',
          'Revise the supplier questionnaires within the limit of the voluntary standards',
          'Follow the Italian transposition of the amendments, due by 19 March 2027',
        ],
      },
      deadline: '2027-01-01',
      deadlineConfirmed: true,
      cross,
      citations,
      confidence: 0.86,
      expertReview: false,
    }
  }

  if (scope === 'below') {
    const employees = profile?.employee_count ?? 0
    const isProtected = employees <= CSRD_EMPLOYEES
    return {
      applicability: 'NO',
      urgency: 'LOW',
      reason: {
        it: `${who.it} non supera entrambe le soglie: nessun obbligo diretto di rendicontazione di sostenibilità.`,
        en: `${who.en} does not exceed both thresholds: no direct sustainability reporting obligation.`,
      },
      impact: {
        it:
          'Le soglie sono cumulative: più di 1.000 dipendenti e più di 450 milioni di euro di ricavi netti. ' +
          (isProtected
            ? "Restano possibili le richieste di dati dei clienti obbligati: un'impresa fino a 1.000 dipendenti può rifiutare ciò che supera i principi volontari del Regolamento delegato (UE) 2026/1560. "
            : "Con più di 1.000 dipendenti l'impresa non è però tra quelle protette dal limite sulle richieste di dati dei clienti obbligati. ") +
          'In Italia il D.L. 23 ottobre 2026, n. 193 ha escluso le imprese sotto soglia dal D.Lgs. 125/2024 per gli esercizi che iniziano nel 2026 e nel 2027; il decreto-legge va convertito entro il 22 dicembre 2026.',
        en:
          'The thresholds are cumulative: more than 1,000 employees and a net turnover above EUR 450 million. ' +
          (isProtected
            ? 'Data requests from customers that have to report remain possible: an undertaking with up to 1,000 employees may decline what goes beyond the voluntary standards of Delegated Regulation (EU) 2026/1560. '
            : 'With more than 1,000 employees, however, the company is not among those protected by the limit on data requests from customers that have to report. ') +
          'In Italy Decree-Law No 193 of 23 October 2026 excluded undertakings below the thresholds from Legislative Decree 125/2024 for financial years starting in 2026 and 2027; the decree-law has to be converted by 22 December 2026.',
      },
      actions: {
        it: [
          'Conservare la verifica delle soglie nel fascicolo del cliente',
          'Rispondere ai questionari dei clienti distinguendo ciò che supera i principi volontari',
          'Rifare la verifica a ogni chiusura di bilancio',
        ],
        en: [
          'Keep the threshold check in the client file',
          'Answer customer questionnaires singling out what goes beyond the voluntary standards',
          'Repeat the check at every balance sheet date',
        ],
      },
      deadline: '',
      deadlineConfirmed: false,
      cross,
      citations: {
        it: [...citations.it, 'D.L. 23 ottobre 2026, n. 193, art. 10'],
        en: [...citations.en, 'Decree-Law No 193 of 23 October 2026, Art. 10'],
      },
      confidence: 0.86,
      expertReview: false,
    }
  }

  return {
    applicability: 'CONDITIONAL',
    urgency: 'MEDIUM',
    reason: {
      it: "Dipende dalle dimensioni: l'obbligo riguarda solo le imprese con più di 1.000 dipendenti e più di 450 milioni di euro di ricavi netti.",
      en: 'It depends on size: the obligation concerns only undertakings with more than 1,000 employees and a net turnover above EUR 450 million.',
    },
    impact: {
      it: "Le due soglie sono cumulative e valgono per gli esercizi che iniziano dal 1° gennaio 2027 (Direttiva (UE) 2026/470, in vigore dal 18 marzo 2026). Senza dipendenti e ricavi netti del cliente non si può dire se l'obbligo resta.",
      en: 'The two thresholds are cumulative and apply to financial years starting on or after 1 January 2027 (Directive (EU) 2026/470, in force since 18 March 2026). Without the employees and net turnover of the client it is not possible to say whether the obligation remains.',
    },
    actions: {
      it: ['Scegliere un cliente con dipendenti e ricavi netti indicati', "Confrontare i due dati con le soglie sull'ultimo bilancio approvato"],
      en: ['Choose a client with employees and net turnover filled in', 'Compare both figures with the thresholds on the last approved financial statements'],
    },
    deadline: '',
    deadlineConfirmed: false,
    cross,
    citations,
    confidence: 0.7,
    expertReview: true,
  }
}

// ─── CSDDD ──────────────────────────────────────────────────

function csddd({ profile, who }: Context): Scenario {
  const scope = csdddScope(profile)
  const citations: Texts<string[]> = {
    it: ['Direttiva (UE) 2024/1760, art. 2, par. 1, lett. a)', 'Direttiva (UE) 2024/1760, art. 8, par. 2 bis', 'Direttiva (UE) 2024/1760, art. 37, par. 1'],
    en: ['Directive (EU) 2024/1760, Art. 2(1)(a)', 'Directive (EU) 2024/1760, Art. 8(2a)', 'Directive (EU) 2024/1760, Art. 37(1)'],
  }
  const cross: Texts<string[]> = {
    it: ["CSRD: soglie diverse (più di 1.000 dipendenti e più di 450 milioni di euro di ricavi netti), esercizi dal 1° gennaio 2027"],
    en: ['CSRD: different thresholds (more than 1,000 employees and a net turnover above EUR 450 million), financial years from 1 January 2027'],
  }
  const calendar: Texts<string> = {
    it: 'Gli Stati membri recepiscono entro il 26 luglio 2028 e le regole si applicano dal 26 luglio 2029.',
    en: 'Member States transpose by 26 July 2028 and the rules apply from 26 July 2029.',
  }

  if (scope === 'above') {
    return {
      applicability: 'YES',
      urgency: 'MEDIUM',
      reason: {
        it: `${who.it} supera entrambe le soglie del dovere di diligenza.`,
        en: `${who.en} exceeds both due diligence thresholds.`,
      },
      impact: {
        it: `Dopo la Direttiva (UE) 2026/470 la CSDDD riguarda le società con più di 5.000 dipendenti e un fatturato netto mondiale superiore a 1,5 miliardi di euro. ${calendar.it} L'obbligo di adottare un piano di transizione climatica (articolo 22) è stato soppresso.`,
        en: `After Directive (EU) 2026/470 the CSDDD covers companies with more than 5,000 employees and a net worldwide turnover above EUR 1.5 billion. ${calendar.en} The obligation to adopt a climate transition plan (Article 22) has been deleted.`,
      },
      actions: {
        it: [
          'Verificare le soglie su due esercizi consecutivi (art. 2, par. 5)',
          "Impostare l'esercizio esplorativo sui settori a maggior rischio (art. 8)",
          'Seguire il recepimento nazionale, dovuto entro il 26 luglio 2028',
        ],
        en: [
          'Check the thresholds over two consecutive financial years (Art. 2(5))',
          'Set up the scoping exercise on the areas of highest risk (Art. 8)',
          'Follow the national transposition, due by 26 July 2028',
        ],
      },
      deadline: '2029-07-26',
      deadlineConfirmed: true,
      cross,
      citations,
      confidence: 0.86,
      expertReview: true,
    }
  }

  if (scope === 'below') {
    return {
      applicability: 'NO',
      urgency: 'LOW',
      reason: {
        it: `${who.it} è sotto le soglie del dovere di diligenza: nessun obbligo diretto.`,
        en: `${who.en} is below the due diligence thresholds: no direct obligation.`,
      },
      impact: {
        it: `La CSDDD riguarda le società con più di 5.000 dipendenti e un fatturato netto mondiale superiore a 1,5 miliardi di euro. ${calendar.it} Come partner commerciale di una società in ambito, l'impresa potrà ricevere richieste di informazioni solo se necessarie e, avendo meno di 5.000 dipendenti, solo se non ottenibili in altro modo.`,
        en: `The CSDDD covers companies with more than 5,000 employees and a net worldwide turnover above EUR 1.5 billion. ${calendar.en} As a business partner of a company in scope, the company may receive information requests only where necessary and, having fewer than 5,000 employees, only when the information cannot be obtained by other means.`,
      },
      actions: {
        it: ['Conservare la verifica delle soglie nel fascicolo del cliente', 'Leggere le clausole sul codice di condotta nei contratti con i grandi clienti'],
        en: ['Keep the threshold check in the client file', 'Read the code of conduct clauses in the contracts with large customers'],
      },
      deadline: '',
      deadlineConfirmed: false,
      cross,
      citations,
      confidence: 0.86,
      expertReview: false,
    }
  }

  return {
    applicability: 'CONDITIONAL',
    urgency: 'LOW',
    reason: {
      it: 'Dipende dalle dimensioni: la direttiva riguarda le società con più di 5.000 dipendenti e un fatturato netto mondiale superiore a 1,5 miliardi di euro.',
      en: 'It depends on size: the directive covers companies with more than 5,000 employees and a net worldwide turnover above EUR 1.5 billion.',
    },
    impact: {
      it: `${calendar.it} Senza dipendenti e fatturato del cliente non si può dire se rientra.`,
      en: `${calendar.en} Without the employees and turnover of the client it is not possible to say whether it is in scope.`,
    },
    actions: {
      it: ['Scegliere un cliente con dipendenti e fatturato indicati'],
      en: ['Choose a client with employees and turnover filled in'],
    },
    deadline: '',
    deadlineConfirmed: false,
    cross,
    citations,
    confidence: 0.7,
    expertReview: true,
  }
}

// ─── Taxonomy ───────────────────────────────────────────────

function taxonomy({ profile, who }: Context): Scenario {
  const scope = csrdScope(profile)
  const citations: Texts<string[]> = {
    it: ['Regolamento (UE) 2020/852, art. 8, par. 1 e 2', 'Direttiva 2013/34/UE, art. 19 bis, par. 1'],
    en: ['Regulation (EU) 2020/852, Art. 8(1) and (2)', 'Directive 2013/34/EU, Art. 19a(1)'],
  }
  const cross: Texts<string[]> = {
    it: ['CSRD: stesso perimetro (più di 1.000 dipendenti e più di 450 milioni di euro di ricavi netti)'],
    en: ['CSRD: same scope (more than 1,000 employees and a net turnover above EUR 450 million)'],
  }
  const rule: Texts<string> = {
    it: "L'informativa dell'articolo 8 (quota di fatturato, di spese in conto capitale e di spese operative da attività ecosostenibili) è dovuta dalle imprese soggette alla rendicontazione di sostenibilità.",
    en: 'The disclosure of Article 8 (share of turnover, of capital expenditure and of operating expenditure from environmentally sustainable activities) is due from the undertakings subject to sustainability reporting.',
  }

  if (scope === 'above') {
    return {
      applicability: 'YES',
      urgency: 'MEDIUM',
      reason: {
        it: `${who.it} è soggetta alla rendicontazione di sostenibilità e quindi all'informativa sulla Tassonomia.`,
        en: `${who.en} is subject to sustainability reporting and therefore to the Taxonomy disclosure.`,
      },
      impact: { it: rule.it, en: rule.en },
      actions: {
        it: ['Classificare le attività rispetto ai criteri di vaglio tecnico', 'Collegare fatturato e spese alle attività classificate'],
        en: ['Classify the activities against the technical screening criteria', 'Link turnover and expenditure to the classified activities'],
      },
      deadline: '',
      deadlineConfirmed: false,
      cross,
      citations,
      confidence: 0.84,
      expertReview: true,
    }
  }
  if (scope === 'below') {
    return {
      applicability: 'NO',
      urgency: 'INFORMATIONAL',
      reason: {
        it: `${who.it} non è soggetta alla rendicontazione di sostenibilità: l'informativa sulla Tassonomia non è dovuta.`,
        en: `${who.en} is not subject to sustainability reporting: the Taxonomy disclosure is not due.`,
      },
      impact: {
        it: `${rule.it} Banche e clienti possono comunque chiedere dati: rispondere è una scelta, non un obbligo di legge.`,
        en: `${rule.en} Banks and customers may still ask for data: answering is a choice, not a legal obligation.`,
      },
      actions: {
        it: ['Conservare la verifica delle soglie nel fascicolo del cliente'],
        en: ['Keep the threshold check in the client file'],
      },
      deadline: '',
      deadlineConfirmed: false,
      cross,
      citations,
      confidence: 0.84,
      expertReview: false,
    }
  }
  return {
    applicability: 'CONDITIONAL',
    urgency: 'LOW',
    reason: {
      it: "Dipende dalle dimensioni: l'informativa è dovuta solo dalle imprese soggette alla rendicontazione di sostenibilità.",
      en: 'It depends on size: the disclosure is due only from the undertakings subject to sustainability reporting.',
    },
    impact: { it: rule.it, en: rule.en },
    actions: {
      it: ['Scegliere un cliente con dipendenti e ricavi netti indicati'],
      en: ['Choose a client with employees and net turnover filled in'],
    },
    deadline: '',
    deadlineConfirmed: false,
    cross,
    citations,
    confidence: 0.7,
    expertReview: true,
  }
}

// ─── AI Act ─────────────────────────────────────────────────

function aiAct({ who }: Context): Scenario {
  return {
    applicability: 'CONDITIONAL',
    urgency: 'MEDIUM',
    reason: {
      it: `Dipende dai sistemi di IA che ${who.it} fornisce o usa, non dalle dimensioni.`,
      en: `It depends on the AI systems that ${who.en} provides or uses, not on size.`,
    },
    impact: {
      it: "Gli obblighi di trasparenza dell'articolo 50 valgono dal 2 agosto 2026; chi fornisce sistemi che generano contenuti e li aveva già sul mercato prima di quella data deve adeguarsi all'articolo 50, paragrafo 2, entro il 2 dicembre 2026. Dopo il Regolamento (UE) 2026/1744 gli obblighi per i sistemi ad alto rischio si applicano dal 2 dicembre 2027 (allegato III) e dal 2 agosto 2028 (allegato I). Per le PMI ogni sanzione è limitata al minore tra importo e percentuale.",
      en: 'The transparency obligations of Article 50 apply from 2 August 2026; providers of systems that generate content and already had them on the market before that date must comply with Article 50(2) by 2 December 2026. After Regulation (EU) 2026/1744 the obligations for high-risk systems apply from 2 December 2027 (Annex III) and from 2 August 2028 (Annex I). For SMEs each fine is capped at the lower of the amount and the percentage.',
    },
    actions: {
      it: [
        "Elencare i sistemi di IA in uso e il ruolo dell'impresa (fornitore o deployer)",
        "Verificare l'avviso alle persone per assistenti virtuali e contenuti generati (art. 50)",
        "Controllare se un sistema rientra nell'allegato III, per esempio la selezione del personale",
        "Mettere per iscritto le misure di alfabetizzazione in materia di IA (art. 4)",
      ],
      en: [
        'List the AI systems in use and the role of the company (provider or deployer)',
        'Check the notice to people for virtual assistants and generated content (Art. 50)',
        'Check whether a system falls under Annex III, for example recruitment',
        'Put the AI literacy measures in writing (Art. 4)',
      ],
    },
    deadline: '2027-12-02',
    deadlineConfirmed: true,
    cross: {
      it: ["GDPR: un sistema di IA che tratta dati personali resta soggetto al regolamento sulla protezione dei dati"],
      en: ['GDPR: an AI system that processes personal data remains subject to the data protection regulation'],
    },
    citations: {
      it: ['Regolamento (UE) 2024/1689, art. 50', 'Regolamento (UE) 2024/1689, art. 111, par. 4', 'Regolamento (UE) 2024/1689, art. 113', 'Regolamento (UE) 2024/1689, art. 99, par. 6'],
      en: ['Regulation (EU) 2024/1689, Art. 50', 'Regulation (EU) 2024/1689, Art. 111(4)', 'Regulation (EU) 2024/1689, Art. 113', 'Regulation (EU) 2024/1689, Art. 99(6)'],
    },
    confidence: 0.82,
    expertReview: true,
  }
}

// ─── GDPR ───────────────────────────────────────────────────

function gdpr({ who }: Context): Scenario {
  return {
    applicability: 'YES',
    urgency: 'MEDIUM',
    reason: {
      it: `Il GDPR si applica a ogni impresa che tratta dati personali: ${who.it} è in ambito.`,
      en: `The GDPR applies to every company that processes personal data: ${who.en} is in scope.`,
    },
    impact: {
      it: "Il regolamento si applica dal 25 maggio 2018, senza soglie dimensionali. Quali adempimenti tocca la novità va letto sul testo: registro dei trattamenti (articolo 30), accordi con i responsabili (articolo 28), notifica delle violazioni entro 72 ore (articolo 33), valutazione d'impatto (articolo 35).",
      en: 'The regulation applies from 25 May 2018, with no size thresholds. Which duties the change touches has to be read in its text: records of processing (Article 30), agreements with processors (Article 28), breach notification within 72 hours (Article 33), impact assessment (Article 35).',
    },
    actions: {
      it: ['Individuare gli articoli che la novità modifica o interpreta', 'Confrontarli con il registro dei trattamenti del cliente'],
      en: ['Identify the articles the change amends or interprets', 'Compare them with the records of processing of the client'],
    },
    deadline: '',
    deadlineConfirmed: false,
    cross: {
      it: ['NIS2: per i soggetti in ambito, un incidente che è anche violazione di dati personali richiede due notifiche distinte (CSIRT Italia e Garante)'],
      en: ['NIS2: for entities in scope, an incident that is also a personal data breach requires two separate notifications (CSIRT Italia and the data protection authority)'],
    },
    citations: {
      it: ['Regolamento (UE) 2016/679, art. 99', 'Regolamento (UE) 2016/679, artt. 28, 30, 33 e 35'],
      en: ['Regulation (EU) 2016/679, Art. 99', 'Regulation (EU) 2016/679, Arts. 28, 30, 33 and 35'],
    },
    confidence: 0.8,
    expertReview: false,
  }
}

// ─── NIS2 ───────────────────────────────────────────────────

function nis2({ profile, who }: Context): Scenario {
  const scope = nis2Scope(profile)
  const citations: Texts<string[]> = {
    it: ['D.Lgs. 4 settembre 2024, n. 138, art. 3', 'D.Lgs. 138/2024, art. 7, comma 1', 'D.Lgs. 138/2024, artt. 24 e 25', 'Direttiva (UE) 2022/2555, art. 2 e art. 23'],
    en: ['Legislative Decree No 138 of 4 September 2024, Art. 3', 'Legislative Decree 138/2024, Art. 7(1)', 'Legislative Decree 138/2024, Arts. 24 and 25', 'Directive (EU) 2022/2555, Art. 2 and Art. 23'],
  }
  const cross: Texts<string[]> = {
    it: ['GDPR: la notifica al CSIRT Italia non sostituisce quella al Garante per le violazioni di dati personali'],
    en: ['GDPR: the notification to CSIRT Italia does not replace the one to the data protection authority for personal data breaches'],
  }
  const duties: Texts<string> = {
    it: "I soggetti in ambito adottano le misure dell'articolo 24, notificano gli incidenti significativi al CSIRT Italia (pre-notifica entro 24 ore, notifica entro 72 ore, relazione finale entro un mese) e aggiornano ogni anno la registrazione sulla piattaforma dell'Agenzia per la cybersicurezza nazionale, dal 1° gennaio al 28 febbraio.",
    en: 'Entities in scope adopt the measures of Article 24, notify significant incidents to CSIRT Italia (early warning within 24 hours, notification within 72 hours, final report within one month) and update every year their registration on the platform of the National Cybersecurity Agency, from 1 January to 28 February.',
  }

  if (scope === 'below') {
    return {
      applicability: 'NO',
      urgency: 'LOW',
      reason: {
        it: `${who.it} non supera i massimali delle piccole imprese: di norma il D.Lgs. 138/2024 non si applica.`,
        en: `${who.en} does not exceed the ceilings for small enterprises: as a rule Legislative Decree 138/2024 does not apply.`,
      },
      impact: {
        it: 'Il decreto riguarda i soggetti dei settori degli allegati che superano i massimali delle piccole imprese (meno di 50 addetti e fatturato o totale di bilancio non superiori a 10 milioni di euro). Restano i casi in cui si applica a prescindere dalle dimensioni (articolo 3, commi 5 e seguenti) e le richieste di sicurezza dei clienti in ambito.',
        en: 'The decree covers entities in the sectors of the annexes that exceed the ceilings for small enterprises (fewer than 50 persons and a turnover or balance sheet total not above EUR 10 million). The cases in which it applies regardless of size remain (Article 3(5) and following), and so do the security requests of customers in scope.',
      },
      actions: {
        it: ['Conservare la verifica dimensionale e rifarla se il cliente cresce o entra in un gruppo', 'Verificare che il cliente non rientri nei casi indipendenti dalle dimensioni'],
        en: ['Keep the size check on file and repeat it if the client grows or joins a group', 'Check that the client does not fall under the cases that are independent of size'],
      },
      deadline: '',
      deadlineConfirmed: false,
      cross,
      citations,
      confidence: 0.82,
      expertReview: false,
    }
  }

  const sized = scope === 'above'
  return {
    applicability: 'CONDITIONAL',
    urgency: sized ? 'HIGH' : 'MEDIUM',
    reason: sized
      ? {
          it: `${who.it} supera i massimali delle piccole imprese: rientra se il settore è tra quelli degli allegati del D.Lgs. 138/2024.`,
          en: `${who.en} exceeds the ceilings for small enterprises: it is in scope if its sector is one of those in the annexes of Legislative Decree 138/2024.`,
        }
      : {
          it: 'Dipende da settore e dimensioni: rientrano i soggetti dei settori degli allegati del D.Lgs. 138/2024 che superano i massimali delle piccole imprese.',
          en: 'It depends on sector and size: entities in the sectors of the annexes of Legislative Decree 138/2024 that exceed the ceilings for small enterprises are in scope.',
        },
    impact: { it: duties.it, en: duties.en },
    actions: {
      it: [
        'Confrontare il settore del cliente con gli allegati I e II del decreto',
        'Aggiornare la registrazione sulla piattaforma ACN dal 1° gennaio al 28 febbraio',
        'Scrivere la procedura di notifica degli incidenti al CSIRT Italia',
        "Portare le misure all'approvazione dell'organo di amministrazione (art. 23)",
      ],
      en: [
        'Compare the sector of the client with Annexes I and II of the decree',
        'Update the registration on the ACN platform from 1 January to 28 February',
        'Write the procedure for notifying incidents to CSIRT Italia',
        'Bring the measures to the management body for approval (Art. 23)',
      ],
    },
    deadline: '2027-02-28',
    deadlineConfirmed: true,
    cross,
    citations,
    confidence: 0.8,
    expertReview: true,
  }
}

// ─── DORA ───────────────────────────────────────────────────

function dora({ profile, who }: Context): Scenario {
  const scope = doraScope(profile)
  const citations: Texts<string[]> = {
    it: ['Regolamento (UE) 2022/2554, art. 2', 'Regolamento (UE) 2022/2554, art. 30', 'Regolamento (UE) 2022/2554, art. 64'],
    en: ['Regulation (EU) 2022/2554, Art. 2', 'Regulation (EU) 2022/2554, Art. 30', 'Regulation (EU) 2022/2554, Art. 64'],
  }
  const cross: Texts<string[]> = {
    it: ['NIS2: per le entità finanziarie DORA è l\'atto settoriale che prevale su gestione dei rischi e notifica degli incidenti'],
    en: ['NIS2: for financial entities DORA is the sector-specific act that prevails on risk management and incident notification'],
  }
  if (scope === 'above') {
    return {
      // The sector alone does not prove the company is one of the entities of Article 2.
      applicability: 'CONDITIONAL',
      urgency: 'HIGH',
      reason: {
        it: `${who.it} opera nel settore finanziario: DORA si applica, dal 17 gennaio 2025, se è una delle entità elencate all'articolo 2.`,
        en: `${who.en} operates in the financial sector: DORA applies, from 17 January 2025, if it is one of the entities listed in Article 2.`,
      },
      impact: {
        it: "Il regolamento chiede un quadro per la gestione dei rischi informatici, la segnalazione dei gravi incidenti TIC, i test di resilienza e la gestione dei fornitori terzi, con il registro degli accordi (articolo 28, paragrafo 3) e il contenuto minimo dei contratti (articolo 30).",
        en: 'The regulation requires an ICT risk management framework, the reporting of major ICT-related incidents, resilience testing and the management of third-party providers, with the register of arrangements (Article 28(3)) and the minimum content of contracts (Article 30).',
      },
      actions: {
        it: ["Confermare la tipologia di entità rispetto all'elenco dell'articolo 2", 'Verificare registro degli accordi e clausole dei contratti TIC'],
        en: ['Confirm the type of entity against the list of Article 2', 'Check the register of arrangements and the clauses of the ICT contracts'],
      },
      deadline: '',
      deadlineConfirmed: false,
      cross,
      citations,
      confidence: 0.8,
      expertReview: true,
    }
  }
  if (scope === 'below') {
    return {
      applicability: 'NO',
      urgency: 'LOW',
      reason: {
        it: `${who.it} non opera nel settore finanziario: DORA non le si applica direttamente.`,
        en: `${who.en} does not operate in the financial sector: DORA does not apply to it directly.`,
      },
      impact: {
        it: "Il regolamento riguarda le entità finanziarie elencate all'articolo 2. Tocca un'impresa di altri settori solo se fornisce software o servizi TIC a banche o assicurazioni: in quel caso i contratti devono contenere gli elementi dell'articolo 30.",
        en: 'The regulation covers the financial entities listed in Article 2. It touches a company in another sector only if it supplies software or ICT services to banks or insurers: in that case the contracts must contain the elements of Article 30.',
      },
      actions: {
        it: ['Verificare se tra i clienti ci sono entità finanziarie', "Se sì, confrontare i contratti con gli elementi dell'articolo 30"],
        en: ['Check whether the customers include financial entities', 'If so, compare the contracts with the elements of Article 30'],
      },
      deadline: '',
      deadlineConfirmed: false,
      cross,
      citations,
      confidence: 0.8,
      expertReview: false,
    }
  }
  return {
    applicability: 'CONDITIONAL',
    urgency: 'MEDIUM',
    reason: {
      it: "Dipende dal settore: DORA riguarda le entità finanziarie elencate all'articolo 2.",
      en: 'It depends on the sector: DORA covers the financial entities listed in Article 2.',
    },
    impact: {
      it: "Il regolamento si applica dal 17 gennaio 2025. Un'impresa di altri settori ne è toccata solo come fornitore di servizi TIC di un'entità finanziaria (articolo 30).",
      en: 'The regulation applies from 17 January 2025. A company in another sector is touched only as an ICT service provider of a financial entity (Article 30).',
    },
    actions: {
      it: ['Scegliere un cliente con il settore indicato'],
      en: ['Choose a client with the sector filled in'],
    },
    deadline: '',
    deadlineConfirmed: false,
    cross,
    citations,
    confidence: 0.7,
    expertReview: true,
  }
}

// ─── CRA ────────────────────────────────────────────────────

function cra({ who }: Context): Scenario {
  return {
    applicability: 'CONDITIONAL',
    urgency: 'MEDIUM',
    reason: {
      it: `Si applica se ${who.it} mette a disposizione sul mercato prodotti con elementi digitali.`,
      en: `It applies if ${who.en} makes products with digital elements available on the market.`,
    },
    impact: {
      it: "Il Regolamento (UE) 2024/2847 riguarda i prodotti che si collegano, anche indirettamente, a un dispositivo o a una rete. Dall'11 settembre 2026 i fabbricanti notificano le vulnerabilità attivamente sfruttate e gli incidenti gravi (preallarme entro 24 ore, notifica entro 72 ore); il resto del regolamento si applica dall'11 dicembre 2027.",
      en: 'Regulation (EU) 2024/2847 covers products that connect, even indirectly, to a device or a network. Since 11 September 2026 manufacturers notify actively exploited vulnerabilities and severe incidents (early warning within 24 hours, notification within 72 hours); the rest of the regulation applies from 11 December 2027.',
    },
    actions: {
      it: [
        "Elencare i prodotti che rientrano nell'ambito (art. 2)",
        'Stabilire chi notifica vulnerabilità sfruttate e incidenti gravi (art. 14)',
        "Pianificare valutazione dei rischi e documentazione tecnica prima dell'11 dicembre 2027",
      ],
      en: [
        'List the products that are in scope (Art. 2)',
        'Settle who notifies exploited vulnerabilities and severe incidents (Art. 14)',
        'Plan the risk assessment and the technical documentation before 11 December 2027',
      ],
    },
    deadline: '2027-12-11',
    deadlineConfirmed: true,
    cross: {
      it: ['NIS2: riguarda la sicurezza del soggetto, il CRA quella dei prodotti che immette sul mercato'],
      en: ['NIS2: it concerns the security of the entity, the CRA that of the products it places on the market'],
    },
    citations: {
      it: ['Regolamento (UE) 2024/2847, art. 2', 'Regolamento (UE) 2024/2847, art. 14', 'Regolamento (UE) 2024/2847, art. 71'],
      en: ['Regulation (EU) 2024/2847, Art. 2', 'Regulation (EU) 2024/2847, Art. 14', 'Regulation (EU) 2024/2847, Art. 71'],
    },
    confidence: 0.8,
    expertReview: true,
  }
}

const SCENARIOS: Record<Topic, (context: Context) => Scenario> = {
  csrd,
  csddd,
  taxonomy,
  ai_act: aiAct,
  gdpr,
  nis2,
  dora,
  cra,
}

/** Which act a pasted text names. The most specific names are tried first. */
const TOPIC_PATTERNS: Array<[Topic, RegExp]> = [
  ['nis2', /\bnis ?2\b|2022\/2555|138\/2024|cybersicurezza|cibersicurezza|cybersecurity|sicurezza informatica/],
  ['dora', /\bdora\b|2022\/2554|digital operational|resilienza operativa/],
  ['cra', /\bcra\b|2024\/2847|cyber resilience|ciberresilienza|elementi digitali|digital elements/],
  ['ai_act', /\bai act\b|2024\/1689|2026\/1744|artificial intelligence|intelligenza artificiale|sistem[ai] di ia\b|ai systems?\b|alto rischio|high-risk/],
  ['csddd', /\bcsddd\b|2024\/1760|due diligence|dovere di diligenza|catena di attivit/],
  ['taxonomy', /taxonomy|tassonomia|2020\/852|vaglio tecnico|screening criteria/],
  ['gdpr', /\bgdpr\b|2016\/679|data protection|protezione dei dati|protezione dati|privacy|dati personali|personal data/],
  ['csrd', /\bcsrd\b|omnibus|2026\/470|2022\/2464|125\/2024|esrs|sustainability reporting|rendicontazione|sogli[ae]/],
]

export function monitorTopicOf(text: string): Topic | null {
  const t = text.toLowerCase()
  for (const [topic, pattern] of TOPIC_PATTERNS) if (pattern.test(t)) return topic
  return null
}

const NOT_RECOGNISED: Texts<Omit<MonitorResponse, 'applicability' | 'urgency' | 'deadline' | 'deadline_is_confirmed' | 'confidence_score' | 'requires_expert_review'>> = {
  it: {
    applicability_reason: 'La demo non ha riconosciuto di quale atto parla il testo.',
    impact_summary:
      'Questa è una demo con dati di esempio: riconosce i testi che nominano CSRD, CSDDD, Tassonomia, AI Act, GDPR, NIS2, DORA o CRA e mostra come si legge la loro applicabilità al profilo scelto. Non interpreta il testo incollato.',
    required_actions: ["Indicare nel testo l'atto o la sigla a cui la novità si riferisce"],
    cross_framework_impacts: [],
    citations: [],
  },
  en: {
    applicability_reason: 'The demo did not recognise which act the text is about.',
    impact_summary:
      'This is a demo with sample data: it recognises texts that name the CSRD, the CSDDD, the Taxonomy, the AI Act, the GDPR, NIS2, DORA or the CRA and shows how their applicability to the chosen profile is read. It does not interpret the text that was pasted.',
    required_actions: ['Name in the text the act or the acronym the change refers to'],
    cross_framework_impacts: [],
    citations: [],
  },
}

/**
 * The demo answer for a regulatory change. `profile` is the company the
 * analysis is about (the API client can pass the `company_profile` of the
 * request); `language` defaults to the interface language. Without a text
 * the CSRD example of the page is used.
 */
export function getMockMonitorResponse(
  changeText?: string,
  profile?: DemoProfile,
  language: Language = demoLanguage(),
): MonitorResponse {
  const topic = changeText ? monitorTopicOf(changeText) : 'csrd'
  if (!topic) {
    return {
      ...NOT_RECOGNISED[language],
      applicability: 'CONDITIONAL',
      urgency: 'LOW',
      deadline: '',
      deadline_is_confirmed: false,
      confidence_score: 0.5,
      requires_expert_review: true,
    }
  }
  const scenario = SCENARIOS[topic](contextOf(profile))
  return {
    applicability: scenario.applicability,
    applicability_reason: scenario.reason[language],
    urgency: scenario.urgency,
    impact_summary: `${scenario.impact[language]} ${DEMO_NOTE[language]}`,
    required_actions: scenario.actions[language],
    deadline: scenario.deadline,
    deadline_is_confirmed: scenario.deadlineConfirmed,
    cross_framework_impacts: scenario.cross[language],
    confidence_score: scenario.confidence,
    requires_expert_review: scenario.expertReview,
    citations: scenario.citations[language],
  }
}
