/**
 * Demo gap analyses, one per framework, Italian and English. The findings
 * are examples, but what they say about the law is not: thresholds, dates
 * and article numbers were read on the official texts on 2026-11-11 (see
 * scope.ts for the thresholds). When the caller passes the company profile,
 * the analysis first says whether the framework applies to a company of that
 * size; without a profile it says which companies it applies to and goes on
 * with the case of a company in scope.
 */
import type { Language } from '@/i18n/config'
import type { ComplianceStatus, GapAnalysisResponse, Requirement } from '../types'
import { demoLanguage } from './language'
import { companyName, csdddScope, csrdScope, describeSize, doraScope, nis2Scope, type Scope } from './scope'
import type { DemoProfile } from './types'

type Priority = Requirement['priority']

interface RowText {
  description: string
  article: string
  gap?: string
  effort?: string
  evidence?: string
}

interface Row {
  id: string
  status: ComplianceStatus
  priority: Priority
  it: RowText
  en: RowText
}

interface Analysis {
  score: number
  rows: Row[]
  recommendations: Record<Language, string[]>
}

type Builder = (profile: DemoProfile | undefined) => Analysis

/** The row that states the scope: computed from the profile, or left to be checked without one. */
function scopeRow(
  id: string,
  scope: Scope,
  profile: DemoProfile | undefined,
  text: Record<Scope, Record<Language, (who: string, size: string) => RowText>>,
  /** Status when the size is above the thresholds: the check is done, unless something else is still open. */
  aboveStatus: ComplianceStatus = 'COMPLIANT',
): Row {
  const status: ComplianceStatus = scope === 'above' ? aboveStatus : scope === 'below' ? 'NOT_APPLICABLE' : 'IN_EVOLUTION'
  return {
    id,
    status,
    priority: scope === 'unknown' ? 'P1' : 'P4',
    it: text[scope].it(companyName(profile, 'it'), describeSize(profile, 'it')),
    en: text[scope].en(companyName(profile, 'en'), describeSize(profile, 'en')),
  }
}

// ─── GDPR ───────────────────────────────────────────────────

const gdpr: Builder = () => ({
  score: 58,
  rows: [
    {
      id: 'GDPR-001',
      status: 'PARTIALLY_COMPLIANT',
      priority: 'P2',
      it: {
        description: 'Registro delle attività di trattamento',
        article: 'art. 30',
        gap: "Il registro esiste ma non comprende i trattamenti avviati nell'ultimo anno",
        effort: '1-2 settimane',
        evidence: 'Registro aggiornato al 2025',
      },
      en: {
        description: 'Records of processing activities',
        article: 'Art. 30',
        gap: 'The record exists but does not include the processing started in the last year',
        effort: '1-2 weeks',
        evidence: 'Record updated to 2025',
      },
    },
    {
      id: 'GDPR-002',
      status: 'COMPLIANT',
      priority: 'P4',
      it: { description: 'Informative agli interessati', article: 'artt. 13 e 14', evidence: 'Informative per clienti, dipendenti e sito' },
      en: { description: 'Information given to data subjects', article: 'Arts. 13 and 14', evidence: 'Notices for customers, employees and website' },
    },
    {
      id: 'GDPR-003',
      status: 'NON_COMPLIANT',
      priority: 'P1',
      it: {
        description: 'Accordi con i responsabili del trattamento',
        article: 'art. 28',
        gap: "Per alcuni fornitori che trattano dati per conto dell'impresa manca l'accordo scritto",
        effort: '2-3 settimane',
      },
      en: {
        description: 'Agreements with processors',
        article: 'Art. 28',
        gap: 'For some suppliers that process data on behalf of the company the written agreement is missing',
        effort: '2-3 weeks',
      },
    },
    {
      id: 'GDPR-004',
      status: 'PARTIALLY_COMPLIANT',
      priority: 'P1',
      it: {
        description: 'Notifica delle violazioni dei dati personali',
        article: 'artt. 33 e 34',
        gap: 'Nessuna procedura scritta: non è stabilito chi decide e chi invia la notifica entro 72 ore',
        effort: '1 settimana',
      },
      en: {
        description: 'Notification of personal data breaches',
        article: 'Arts. 33 and 34',
        gap: 'No written procedure: it is not settled who decides and who sends the notification within 72 hours',
        effort: '1 week',
      },
    },
    {
      id: 'GDPR-005',
      status: 'IN_EVOLUTION',
      priority: 'P2',
      it: {
        description: "Valutazione d'impatto sulla protezione dei dati",
        article: 'art. 35',
        gap: 'Da stabilire se qualche trattamento presenta un rischio elevato e richiede la valutazione',
        effort: '2-4 settimane',
      },
      en: {
        description: 'Data protection impact assessment',
        article: 'Art. 35',
        gap: 'To be established whether any processing is likely to result in a high risk and needs the assessment',
        effort: '2-4 weeks',
      },
    },
    {
      id: 'GDPR-006',
      status: 'IN_EVOLUTION',
      priority: 'P3',
      it: {
        description: 'Responsabile della protezione dei dati',
        article: 'art. 37',
        gap: "La designazione è obbligatoria solo nei casi dell'articolo 37, paragrafo 1: valutazione da mettere per iscritto",
        effort: '1 settimana',
      },
      en: {
        description: 'Data protection officer',
        article: 'Art. 37',
        gap: 'Designation is mandatory only in the cases of Article 37(1): the assessment should be put in writing',
        effort: '1 week',
      },
    },
  ],
  recommendations: {
    it: [
      "Firma l'accordo sul trattamento con i fornitori che trattano dati per conto dell'impresa (art. 28).",
      "Scrivi la procedura per le violazioni: chi valuta, chi notifica all'autorità di controllo entro 72 ore (art. 33).",
      "Aggiorna il registro con i trattamenti avviati nell'ultimo anno (art. 30).",
      "Metti per iscritto se serve una valutazione d'impatto e se va designato un responsabile della protezione dei dati (artt. 35 e 37).",
    ],
    en: [
      'Sign the processing agreement with the suppliers that process data on behalf of the company (Art. 28).',
      'Write the breach procedure: who assesses, who notifies the supervisory authority within 72 hours (Art. 33).',
      'Update the record with the processing started in the last year (Art. 30).',
      'Put in writing whether an impact assessment is needed and whether a data protection officer must be designated (Arts. 35 and 37).',
    ],
  },
})

// ─── AI Act ─────────────────────────────────────────────────

const aiAct: Builder = () => ({
  score: 42,
  rows: [
    {
      id: 'AI-001',
      status: 'IN_EVOLUTION',
      priority: 'P1',
      it: {
        description: "Ruolo dell'impresa per ogni sistema di IA in uso (fornitore o deployer)",
        article: 'art. 3, punti 3) e 4)',
        gap: 'Non esiste un elenco dei sistemi in uso: senza non si può dire quali obblighi valgono',
        effort: '1-2 settimane',
      },
      en: {
        description: 'Role of the company for each AI system in use (provider or deployer)',
        article: 'Art. 3, points (3) and (4)',
        gap: 'There is no list of the systems in use: without it nobody can say which obligations apply',
        effort: '1-2 weeks',
      },
    },
    {
      id: 'AI-002',
      status: 'PARTIALLY_COMPLIANT',
      priority: 'P1',
      it: {
        description: 'Trasparenza verso le persone: assistenti virtuali e contenuti generati',
        article: 'art. 50',
        gap: "L'assistente sul sito non dice all'avvio di essere un sistema di IA; obbligo in applicazione dal 2 agosto 2026",
        effort: '1 settimana',
      },
      en: {
        description: 'Transparency towards people: virtual assistants and generated content',
        article: 'Art. 50',
        gap: 'The assistant on the website does not say at the start that it is an AI system; obligation applicable since 2 August 2026',
        effort: '1 week',
      },
    },
    {
      id: 'AI-003',
      status: 'PARTIALLY_COMPLIANT',
      priority: 'P2',
      it: {
        description: 'Alfabetizzazione in materia di IA',
        article: 'art. 4',
        gap: 'Istruzioni date a voce: nessuna traccia delle misure adottate per chi usa i sistemi',
        effort: '2 settimane',
      },
      en: {
        description: 'AI literacy',
        article: 'Art. 4',
        gap: 'Instructions given orally: no record of the measures taken for the people who use the systems',
        effort: '2 weeks',
      },
    },
    {
      id: 'AI-004',
      status: 'COMPLIANT',
      priority: 'P4',
      it: { description: 'Pratiche di IA vietate', article: 'art. 5', evidence: 'Nessun uso tra quelli vietati' },
      en: { description: 'Prohibited AI practices', article: 'Art. 5', evidence: 'No use among the prohibited ones' },
    },
    {
      id: 'AI-005',
      status: 'IN_EVOLUTION',
      priority: 'P3',
      it: {
        description: "Sistemi ad alto rischio dell'allegato III",
        article: 'artt. 6 e 26',
        gap: "Da verificare se un sistema in uso rientra nell'allegato III (per esempio la selezione del personale): gli obblighi si applicano dal 2 dicembre 2027",
        effort: '2-3 settimane',
      },
      en: {
        description: 'High-risk systems of Annex III',
        article: 'Arts. 6 and 26',
        gap: 'To be checked whether a system in use falls under Annex III (for example recruitment): the obligations apply from 2 December 2027',
        effort: '2-3 weeks',
      },
    },
  ],
  recommendations: {
    it: [
      "Compila l'elenco dei sistemi di IA in uso, con fornitore, scopo e ruolo dell'impresa.",
      "Fai comparire all'avvio dell'assistente l'avviso che si sta parlando con un sistema di IA (art. 50, par. 1).",
      'Metti per iscritto le istruzioni per chi usa i sistemi e conserva traccia delle misure adottate (art. 4).',
      "Controlla prima del 2 dicembre 2027 se qualche sistema rientra nell'allegato III.",
    ],
    en: [
      'Draw up the list of the AI systems in use, with provider, purpose and role of the company.',
      'Have the assistant show at the start the notice that the person is talking to an AI system (Art. 50(1)).',
      'Put in writing the instructions for the people who use the systems and keep a record of the measures taken (Art. 4).',
      'Check before 2 December 2027 whether any system falls under Annex III.',
    ],
  },
})

// ─── NIS2 ───────────────────────────────────────────────────

const nis2: Builder = (profile) => {
  const scope = nis2Scope(profile)
  const first = scopeRow('NIS2-001', scope, profile, {
    above: {
      it: (who, size) => ({
        description: 'Ambito di applicazione e registrazione annuale',
        article: 'D.Lgs. 138/2024, artt. 3 e 7',
        gap: `${who} (${size}) supera i massimali delle piccole imprese: rientra se il settore è tra quelli degli allegati. Registrazione da aggiornare dal 1° gennaio al 28 febbraio di ogni anno`,
        effort: '1 settimana',
      }),
      en: (who, size) => ({
        description: 'Scope and yearly registration',
        article: 'Legislative Decree 138/2024, Arts. 3 and 7',
        gap: `${who} (${size}) exceeds the ceilings for small enterprises: it is in scope if its sector is one of those in the annexes. Registration to be updated from 1 January to 28 February of each year`,
        effort: '1 week',
      }),
    },
    below: {
      it: (who, size) => ({
        description: 'Ambito di applicazione',
        article: 'D.Lgs. 138/2024, art. 3',
        gap: `${who} (${size}) non supera i massimali delle piccole imprese: di norma è fuori ambito, salvo i casi in cui il decreto si applica a prescindere dalle dimensioni (art. 3, commi 5 e seguenti)`,
      }),
      en: (who, size) => ({
        description: 'Scope',
        article: 'Legislative Decree 138/2024, Art. 3',
        gap: `${who} (${size}) does not exceed the ceilings for small enterprises: as a rule it is out of scope, except where the decree applies regardless of size (Art. 3(5) and following)`,
      }),
    },
    unknown: {
      it: () => ({
        description: 'Ambito di applicazione e registrazione annuale',
        article: 'D.Lgs. 138/2024, artt. 3 e 7',
        gap: 'Da verificare: rientrano i soggetti dei settori degli allegati che superano i massimali delle piccole imprese. Le righe seguenti descrivono un soggetto in ambito',
        effort: '1 settimana',
      }),
      en: () => ({
        description: 'Scope and yearly registration',
        article: 'Legislative Decree 138/2024, Arts. 3 and 7',
        gap: 'To be checked: entities in the sectors of the annexes that exceed the ceilings for small enterprises are in scope. The following rows describe an entity in scope',
        effort: '1 week',
      }),
    },
  }, 'IN_EVOLUTION')

  if (scope === 'below') {
    return {
      score: 62,
      rows: [
        first,
        {
          id: 'NIS2-002',
          status: 'IN_EVOLUTION',
          priority: 'P2',
          it: {
            description: 'Richieste di sicurezza dei clienti in ambito',
            article: 'D.Lgs. 138/2024, art. 24, comma 2, lett. d)',
            gap: 'I clienti soggetti al decreto devono curare la sicurezza della catena di approvvigionamento: sono da attendersi clausole e questionari',
            effort: '2 settimane',
          },
          en: {
            description: 'Security requests from customers in scope',
            article: 'Legislative Decree 138/2024, Art. 24(2)(d)',
            gap: 'Customers covered by the decree must look after supply chain security: contract clauses and questionnaires are to be expected',
            effort: '2 weeks',
          },
        },
      ],
      recommendations: {
        it: [
          "Conserva la verifica dimensionale e rifalla se l'impresa cresce o entra in un gruppo.",
          'Prepara risposte documentate ai questionari di sicurezza dei clienti (backup, accessi, gestione degli incidenti).',
        ],
        en: [
          'Keep the size check on file and repeat it if the company grows or joins a group.',
          'Prepare documented answers to the security questionnaires of customers (backups, access, incident handling).',
        ],
      },
    }
  }

  return {
    score: 44,
    rows: [
      first,
      {
        id: 'NIS2-002',
        status: 'PARTIALLY_COMPLIANT',
        priority: 'P1',
        it: {
          description: 'Misure di gestione dei rischi per la sicurezza informatica',
          article: 'D.Lgs. 138/2024, art. 24 (dir. art. 21)',
          gap: "Backup e controllo degli accessi presenti; mancano l'analisi dei rischi e la valutazione dell'efficacia delle misure",
          effort: '6-8 settimane',
        },
        en: {
          description: 'Cybersecurity risk-management measures',
          article: 'Legislative Decree 138/2024, Art. 24 (Directive Art. 21)',
          gap: 'Backups and access control are in place; the risk analysis and the assessment of the effectiveness of the measures are missing',
          effort: '6-8 weeks',
        },
      },
      {
        id: 'NIS2-003',
        status: 'NON_COMPLIANT',
        priority: 'P1',
        it: {
          description: 'Notifica degli incidenti significativi al CSIRT Italia',
          article: 'D.Lgs. 138/2024, art. 25 (dir. art. 23)',
          gap: 'Nessuna procedura per la pre-notifica entro 24 ore, la notifica entro 72 ore e la relazione finale entro un mese',
          effort: '2-3 settimane',
        },
        en: {
          description: 'Notification of significant incidents to CSIRT Italia',
          article: 'Legislative Decree 138/2024, Art. 25 (Directive Art. 23)',
          gap: 'No procedure for the early warning within 24 hours, the notification within 72 hours and the final report within one month',
          effort: '2-3 weeks',
        },
      },
      {
        id: 'NIS2-004',
        status: 'PARTIALLY_COMPLIANT',
        priority: 'P2',
        it: {
          description: 'Organi di amministrazione: approvazione delle misure e formazione',
          article: 'D.Lgs. 138/2024, art. 23 (dir. art. 20)',
          gap: "L'organo di amministrazione non ha ancora approvato le misure né seguito la formazione",
          effort: '2 settimane',
        },
        en: {
          description: 'Management bodies: approval of the measures and training',
          article: 'Legislative Decree 138/2024, Art. 23 (Directive Art. 20)',
          gap: 'The management body has not yet approved the measures nor followed the training',
          effort: '2 weeks',
        },
      },
      {
        id: 'NIS2-005',
        status: 'NON_COMPLIANT',
        priority: 'P2',
        it: {
          description: 'Sicurezza della catena di approvvigionamento',
          article: 'D.Lgs. 138/2024, art. 24, comma 2, lett. d)',
          gap: 'Nessun criterio di sicurezza nella scelta e nei contratti dei fornitori diretti',
          effort: '4-6 settimane',
        },
        en: {
          description: 'Supply chain security',
          article: 'Legislative Decree 138/2024, Art. 24(2)(d)',
          gap: 'No security criteria in the choice of direct suppliers nor in their contracts',
          effort: '4-6 weeks',
        },
      },
      {
        id: 'NIS2-006',
        status: 'COMPLIANT',
        priority: 'P4',
        it: {
          description: 'Autenticazione a più fattori',
          article: 'D.Lgs. 138/2024, art. 24, comma 2, lett. l)',
          evidence: 'Attiva su posta, accesso remoto e gestionale',
        },
        en: {
          description: 'Multi-factor authentication',
          article: 'Legislative Decree 138/2024, Art. 24(2)(l)',
          evidence: 'Active on email, remote access and the management system',
        },
      },
    ],
    recommendations: {
      it: [
        'Scrivi la procedura di notifica al CSIRT Italia: pre-notifica entro 24 ore, notifica entro 72 ore, relazione finale entro un mese (art. 25).',
        "Porta le misure all'approvazione dell'organo di amministrazione e pianifica la sua formazione (art. 23).",
        "Completa l'analisi dei rischi e introduci criteri di sicurezza per i fornitori diretti (art. 24).",
        'Aggiorna la registrazione sulla piattaforma ACN dal 1° gennaio al 28 febbraio (art. 7).',
      ],
      en: [
        'Write the procedure for notifying CSIRT Italia: early warning within 24 hours, notification within 72 hours, final report within one month (Art. 25).',
        'Bring the measures to the management body for approval and plan its training (Art. 23).',
        'Complete the risk analysis and introduce security criteria for direct suppliers (Art. 24).',
        'Update the registration on the ACN platform from 1 January to 28 February (Art. 7).',
      ],
    },
  }
}

// ─── CRA ────────────────────────────────────────────────────

const cra: Builder = () => ({
  score: 36,
  rows: [
    {
      id: 'CRA-001',
      status: 'IN_EVOLUTION',
      priority: 'P1',
      it: {
        description: 'Ambito: prodotti con elementi digitali messi a disposizione sul mercato',
        article: 'art. 2',
        gap: "Da verificare prodotto per prodotto: il regolamento riguarda quelli che si collegano, anche indirettamente, a un dispositivo o a una rete. Le righe seguenti descrivono un fabbricante in ambito",
        effort: '1 settimana',
      },
      en: {
        description: 'Scope: products with digital elements made available on the market',
        article: 'Art. 2',
        gap: 'To be checked product by product: the regulation covers those that connect, even indirectly, to a device or a network. The following rows describe a manufacturer in scope',
        effort: '1 week',
      },
    },
    {
      id: 'CRA-002',
      status: 'NON_COMPLIANT',
      priority: 'P1',
      it: {
        description: 'Segnalazione delle vulnerabilità attivamente sfruttate e degli incidenti gravi',
        article: 'art. 14',
        gap: "Obbligo in applicazione dall'11 settembre 2026: manca il processo per il preallarme entro 24 ore e la notifica entro 72 ore",
        effort: '3-4 settimane',
      },
      en: {
        description: 'Reporting of actively exploited vulnerabilities and severe incidents',
        article: 'Art. 14',
        gap: 'Obligation applicable since 11 September 2026: the process for the early warning within 24 hours and the notification within 72 hours is missing',
        effort: '3-4 weeks',
      },
    },
    {
      id: 'CRA-003',
      status: 'PARTIALLY_COMPLIANT',
      priority: 'P2',
      it: {
        description: 'Gestione delle vulnerabilità e aggiornamenti di sicurezza',
        article: 'art. 13 e allegato I, parte II',
        gap: "Aggiornamenti distribuiti senza un processo scritto e senza aver determinato il periodo di assistenza; requisiti applicabili dall'11 dicembre 2027",
        effort: '6-8 settimane',
      },
      en: {
        description: 'Vulnerability handling and security updates',
        article: 'Art. 13 and Annex I, Part II',
        gap: 'Updates are distributed without a written process and without a determined support period; requirements applicable from 11 December 2027',
        effort: '6-8 weeks',
      },
    },
    {
      id: 'CRA-004',
      status: 'IN_EVOLUTION',
      priority: 'P2',
      it: {
        description: 'Requisiti di cibersicurezza relativi alle proprietà dei prodotti',
        article: 'allegato I, parte I',
        gap: 'Valutazione dei rischi di cibersicurezza del prodotto avviata, non conclusa',
        effort: '8-12 settimane',
      },
      en: {
        description: 'Cybersecurity requirements relating to the properties of products',
        article: 'Annex I, Part I',
        gap: 'The cybersecurity risk assessment of the product has started and is not finished',
        effort: '8-12 weeks',
      },
    },
    {
      id: 'CRA-005',
      status: 'NON_COMPLIANT',
      priority: 'P3',
      it: {
        description: 'Documentazione tecnica e dichiarazione di conformità UE',
        article: 'artt. 31 e 28',
        gap: "Da predisporre prima dell'11 dicembre 2027",
        effort: '4-6 settimane',
      },
      en: {
        description: 'Technical documentation and EU declaration of conformity',
        article: 'Arts. 31 and 28',
        gap: 'To be prepared before 11 December 2027',
        effort: '4-6 weeks',
      },
    },
  ],
  recommendations: {
    it: [
      'Stabilisci chi riceve le segnalazioni di vulnerabilità e chi notifica entro 24 e 72 ore (art. 14).',
      "Elenca i prodotti che rientrano nell'ambito e quelli che ne restano fuori, con il motivo (art. 2).",
      'Scrivi il processo di gestione delle vulnerabilità e determina il periodo di assistenza (art. 13, par. 8).',
      "Pianifica valutazione dei rischi e documentazione tecnica prima dell'11 dicembre 2027.",
    ],
    en: [
      'Settle who receives vulnerability reports and who notifies within 24 and 72 hours (Art. 14).',
      'List the products that are in scope and those that are not, with the reason (Art. 2).',
      'Write the vulnerability handling process and determine the support period (Art. 13(8)).',
      'Plan the risk assessment and the technical documentation before 11 December 2027.',
    ],
  },
})

// ─── CSRD ───────────────────────────────────────────────────

const csrd: Builder = (profile) => {
  const scope = csrdScope(profile)
  const first = scopeRow('CSRD-001', scope, profile, {
    above: {
      it: (who, size) => ({
        description: "Verifica dell'ambito di applicazione",
        article: 'art. 19 bis, par. 1, dir. 2013/34/UE',
        gap: `${who} (${size}) supera entrambe le soglie: primo esercizio con il nuovo perimetro, quello che inizia dal 1° gennaio 2027`,
      }),
      en: (who, size) => ({
        description: 'Scope check',
        article: 'Art. 19a(1) of Directive 2013/34/EU',
        gap: `${who} (${size}) exceeds both thresholds: the first financial year under the new scope is the one starting on or after 1 January 2027`,
      }),
    },
    below: {
      it: (who, size) => ({
        description: 'Obbligo di rendicontazione di sostenibilità',
        article: 'art. 19 bis, par. 1, dir. 2013/34/UE',
        gap: `${who} (${size}) non supera entrambe le soglie (più di 1.000 dipendenti e più di 450 milioni di euro di ricavi netti): nessun obbligo diretto`,
      }),
      en: (who, size) => ({
        description: 'Sustainability reporting obligation',
        article: 'Art. 19a(1) of Directive 2013/34/EU',
        gap: `${who} (${size}) does not exceed both thresholds (more than 1,000 employees and a net turnover above EUR 450 million): no direct obligation`,
      }),
    },
    unknown: {
      it: () => ({
        description: 'Ambito di applicazione',
        article: 'art. 19 bis, par. 1, dir. 2013/34/UE',
        gap: "Da verificare: l'obbligo riguarda solo le imprese con più di 1.000 dipendenti e più di 450 milioni di euro di ricavi netti. Le righe seguenti descrivono un'impresa sopra le soglie",
        effort: '1 settimana',
      }),
      en: () => ({
        description: 'Scope',
        article: 'Art. 19a(1) of Directive 2013/34/EU',
        gap: 'To be checked: the obligation concerns only undertakings with more than 1,000 employees and a net turnover above EUR 450 million. The following rows describe an undertaking above the thresholds',
        effort: '1 week',
      }),
    },
  })

  if (scope === 'below') {
    return {
      score: 55,
      rows: [
        first,
        {
          id: 'CSRD-002',
          status: 'PARTIALLY_COMPLIANT',
          priority: 'P2',
          it: {
            description: 'Richieste di dati dei clienti obbligati alla rendicontazione',
            article: 'art. 19 bis, par. 3, dir. 2013/34/UE',
            gap: "L'impresa risponde ai questionari senza distinguere ciò che supera i principi volontari, che ha il diritto di rifiutare",
            effort: '1-2 settimane',
          },
          en: {
            description: 'Data requests from customers that have to report',
            article: 'Art. 19a(3) of Directive 2013/34/EU',
            gap: 'The company answers the questionnaires without singling out what goes beyond the voluntary standards, which it has the right to decline',
            effort: '1-2 weeks',
          },
        },
        {
          id: 'CSRD-003',
          status: 'IN_EVOLUTION',
          priority: 'P3',
          it: {
            description: 'Dati del modulo base dei principi volontari',
            article: 'reg. delegato (UE) 2026/1560, allegato I',
            gap: 'Uso volontario: dati su energia, emissioni, rifiuti e forza lavoro disponibili solo in parte',
            effort: '3-4 settimane',
          },
          en: {
            description: 'Data of the basic module of the voluntary standard',
            article: 'Delegated Regulation (EU) 2026/1560, Annex I',
            gap: 'Voluntary use: data on energy, emissions, waste and workforce are only partly available',
            effort: '3-4 weeks',
          },
        },
      ],
      recommendations: {
        it: [
          'Rispondi ai questionari dei clienti nel perimetro dei principi volontari e segnala le richieste che lo superano (art. 19 bis, par. 3).',
          'Raccogli una volta l\'anno i dati del modulo base: energia, emissioni, rifiuti, forza lavoro.',
          'Conserva la verifica delle soglie e rifalla a ogni chiusura di bilancio.',
        ],
        en: [
          'Answer customer questionnaires within the perimeter of the voluntary standards and point out the requests that go beyond it (Art. 19a(3)).',
          'Collect the data of the basic module once a year: energy, emissions, waste, workforce.',
          'Keep the threshold check on file and repeat it at every balance sheet date.',
        ],
      },
    }
  }

  return {
    score: 41,
    rows: [
      first,
      {
        id: 'CSRD-002',
        status: 'NON_COMPLIANT',
        priority: 'P1',
        it: {
          description: 'Valutazione della doppia rilevanza',
          article: 'ESRS 1, capitolo 3',
          gap: 'Valutazione non ancora svolta: senza non si sa quali informazioni comunicare',
          effort: '6-8 settimane',
        },
        en: {
          description: 'Double materiality assessment',
          article: 'ESRS 1, chapter 3',
          gap: 'Assessment not yet carried out: without it nobody knows which information to report',
          effort: '6-8 weeks',
        },
      },
      {
        id: 'CSRD-003',
        status: 'PARTIALLY_COMPLIANT',
        priority: 'P2',
        it: {
          description: 'Informazioni sulla catena del valore',
          article: 'art. 19 bis, par. 3, dir. 2013/34/UE',
          gap: 'Questionari ai fornitori da rivedere: alle imprese fino a 1.000 dipendenti non si può chiedere più di quanto previsto dai principi volontari',
          effort: '3-4 settimane',
        },
        en: {
          description: 'Value chain information',
          article: 'Art. 19a(3) of Directive 2013/34/EU',
          gap: 'Supplier questionnaires to be revised: undertakings with up to 1,000 employees cannot be asked for more than the voluntary standards provide',
          effort: '3-4 weeks',
        },
      },
      {
        id: 'CSRD-004',
        status: 'PARTIALLY_COMPLIANT',
        priority: 'P2',
        it: {
          description: 'Emissioni di gas a effetto serra',
          article: 'ESRS E1',
          gap: 'Ambito 1 e 2 calcolati; ambito 3 ancora da stimare',
          effort: '6-8 settimane',
          evidence: 'Inventario delle emissioni 2025',
        },
        en: {
          description: 'Greenhouse gas emissions',
          article: 'ESRS E1',
          gap: 'Scope 1 and 2 calculated; Scope 3 still to be estimated',
          effort: '6-8 weeks',
          evidence: '2025 emissions inventory',
        },
      },
      {
        id: 'CSRD-005',
        status: 'NON_COMPLIANT',
        priority: 'P2',
        it: {
          description: 'Informativa sulle attività ecosostenibili',
          article: 'art. 8 reg. (UE) 2020/852',
          gap: 'Quote di fatturato, spese in conto capitale e spese operative non ancora calcolate',
          effort: '4-6 settimane',
        },
        en: {
          description: 'Disclosure on environmentally sustainable activities',
          article: 'Art. 8 of Regulation (EU) 2020/852',
          gap: 'Shares of turnover, capital expenditure and operating expenditure not yet calculated',
          effort: '4-6 weeks',
        },
      },
      {
        id: 'CSRD-006',
        status: 'IN_EVOLUTION',
        priority: 'P3',
        it: {
          description: 'Attestazione della rendicontazione con un livello di sicurezza limitato',
          article: 'art. 34 dir. 2013/34/UE',
          gap: 'Incarico al revisore da conferire',
          effort: '2 settimane',
        },
        en: {
          description: 'Limited assurance on the sustainability reporting',
          article: 'Art. 34 of Directive 2013/34/EU',
          gap: 'Engagement of the auditor still to be decided',
          effort: '2 weeks',
        },
      },
    ],
    recommendations: {
      it: [
        'Parti dalla valutazione della doppia rilevanza: decide quali informazioni comunicare (ESRS 1, capitolo 3).',
        "Rivedi i questionari ai fornitori: alle imprese fino a 1.000 dipendenti chiedi solo ciò che rientra nei principi volontari (art. 19 bis, par. 3).",
        "Stima le emissioni di ambito 3 e calcola le quote della Tassonomia per l'esercizio 2027.",
        "Scegli con il cliente quale versione degli ESRS applicare per l'esercizio 2026 (reg. delegato (UE) 2026/1563, art. 2).",
      ],
      en: [
        'Start from the double materiality assessment: it decides which information to report (ESRS 1, chapter 3).',
        'Revise the supplier questionnaires: ask undertakings with up to 1,000 employees only for what falls within the voluntary standards (Art. 19a(3)).',
        'Estimate Scope 3 emissions and calculate the Taxonomy shares for financial year 2027.',
        'Choose with the client which version of the ESRS to apply for financial year 2026 (Delegated Regulation (EU) 2026/1563, Art. 2).',
      ],
    },
  }
}

// ─── CSDDD ──────────────────────────────────────────────────

const csddd: Builder = (profile) => {
  const scope = csdddScope(profile)
  const first = scopeRow('CSDDD-001', scope, profile, {
    above: {
      it: (who, size) => ({
        description: "Verifica dell'ambito di applicazione",
        article: 'art. 2, par. 1, lett. a)',
        gap: `${who} (${size}) supera entrambe le soglie: obblighi applicabili dal 26 luglio 2029`,
      }),
      en: (who, size) => ({
        description: 'Scope check',
        article: 'Art. 2(1)(a)',
        gap: `${who} (${size}) exceeds both thresholds: obligations applicable from 26 July 2029`,
      }),
    },
    below: {
      it: (who, size) => ({
        description: 'Obblighi relativi al dovere di diligenza',
        article: 'art. 2, par. 1, lett. a)',
        gap: `${who} (${size}) è sotto le soglie (più di 5.000 dipendenti e fatturato netto mondiale oltre 1,5 miliardi di euro): nessun obbligo diretto`,
      }),
      en: (who, size) => ({
        description: 'Due diligence obligations',
        article: 'Art. 2(1)(a)',
        gap: `${who} (${size}) is below the thresholds (more than 5,000 employees and a net worldwide turnover above EUR 1.5 billion): no direct obligation`,
      }),
    },
    unknown: {
      it: () => ({
        description: 'Ambito di applicazione',
        article: 'art. 2, par. 1, lett. a)',
        gap: 'Da verificare: la direttiva riguarda le società con più di 5.000 dipendenti e fatturato netto mondiale oltre 1,5 miliardi di euro. Le righe seguenti descrivono una società in ambito',
        effort: '1 settimana',
      }),
      en: () => ({
        description: 'Scope',
        article: 'Art. 2(1)(a)',
        gap: 'To be checked: the directive covers companies with more than 5,000 employees and a net worldwide turnover above EUR 1.5 billion. The following rows describe a company in scope',
        effort: '1 week',
      }),
    },
  })

  if (scope === 'below') {
    return {
      score: 60,
      rows: [
        first,
        {
          id: 'CSDDD-002',
          status: 'IN_EVOLUTION',
          priority: 'P3',
          it: {
            description: 'Richieste di informazioni dei clienti in ambito',
            article: 'art. 8, par. 2 bis',
            gap: 'Dal 26 luglio 2029 i clienti obbligati potranno chiedere informazioni solo se necessarie e, ai partner con meno di 5.000 dipendenti, solo se non ottenibili in altro modo',
          },
          en: {
            description: 'Information requests from customers in scope',
            article: 'Art. 8(2a)',
            gap: 'From 26 July 2029 in-scope customers may ask for information only where necessary and, from partners with fewer than 5,000 employees, only when it cannot be obtained by other means',
          },
        },
        {
          id: 'CSDDD-003',
          status: 'IN_EVOLUTION',
          priority: 'P3',
          it: {
            description: 'Garanzie contrattuali chieste ai partner commerciali diretti',
            article: 'art. 10, par. 2, lett. b)',
            gap: 'I clienti in ambito potranno chiedere il rispetto del loro codice di condotta: clausole da leggere prima di firmare',
          },
          en: {
            description: 'Contractual assurances requested from direct business partners',
            article: 'Art. 10(2)(b)',
            gap: 'In-scope customers may ask for compliance with their code of conduct: clauses to be read before signing',
          },
        },
      ],
      recommendations: {
        it: [
          'Nessun obbligo diretto: tieni la verifica delle soglie nel fascicolo del cliente.',
          'Leggi le clausole sul codice di condotta nei contratti con i grandi clienti prima della firma.',
        ],
        en: [
          'No direct obligation: keep the threshold check in the client file.',
          'Read the code of conduct clauses in the contracts with large customers before signing.',
        ],
      },
    }
  }

  return {
    score: 38,
    rows: [
      first,
      {
        id: 'CSDDD-002',
        status: 'PARTIALLY_COMPLIANT',
        priority: 'P2',
        it: {
          description: 'Politica relativa al dovere di diligenza',
          article: 'art. 7',
          gap: 'Codice di condotta presente; manca la descrizione dei processi per attuarlo',
          effort: '6-8 settimane',
        },
        en: {
          description: 'Due diligence policy',
          article: 'Art. 7',
          gap: 'A code of conduct exists; the description of the processes to implement it is missing',
          effort: '6-8 weeks',
        },
      },
      {
        id: 'CSDDD-003',
        status: 'NON_COMPLIANT',
        priority: 'P1',
        it: {
          description: 'Individuazione e valutazione degli impatti negativi',
          article: 'art. 8',
          gap: 'Esercizio esplorativo sui settori a maggior rischio non ancora svolto',
          effort: '8-12 settimane',
        },
        en: {
          description: 'Identifying and assessing adverse impacts',
          article: 'Art. 8',
          gap: 'The scoping exercise on the areas of highest risk has not been carried out yet',
          effort: '8-12 weeks',
        },
      },
      {
        id: 'CSDDD-004',
        status: 'NON_COMPLIANT',
        priority: 'P2',
        it: {
          description: 'Meccanismo di notifica e procedura di reclamo',
          article: 'art. 14',
          gap: 'Nessun canale per i reclami di persone e organizzazioni esterne',
          effort: '4-6 settimane',
        },
        en: {
          description: 'Notification mechanism and complaints procedure',
          article: 'Art. 14',
          gap: 'No channel for complaints from external persons and organisations',
          effort: '4-6 weeks',
        },
      },
      {
        id: 'CSDDD-005',
        status: 'IN_EVOLUTION',
        priority: 'P3',
        it: {
          description: 'Monitoraggio delle misure',
          article: 'art. 15',
          gap: 'Valutazione periodica da impostare: almeno ogni cinque anni e dopo ogni cambiamento significativo',
          effort: '3-4 settimane',
        },
        en: {
          description: 'Monitoring of the measures',
          article: 'Art. 15',
          gap: 'Periodic assessment to be set up: at least every five years and after any significant change',
          effort: '3-4 weeks',
        },
      },
    ],
    recommendations: {
      it: [
        "Avvia l'esercizio esplorativo sui settori in cui gli impatti negativi sono più probabili e più gravi (art. 8).",
        'Apri un canale di reclamo accessibile anche a chi è esterno alla società (art. 14).',
        'Completa la politica con i processi che la attuano (art. 7).',
        'Segui il recepimento nazionale, dovuto entro il 26 luglio 2028.',
      ],
      en: [
        'Start the scoping exercise on the areas where adverse impacts are most likely and most severe (Art. 8).',
        'Open a complaints channel that people outside the company can also use (Art. 14).',
        'Complete the policy with the processes that implement it (Art. 7).',
        'Follow the national transposition, due by 26 July 2028.',
      ],
    },
  }
}

// ─── Taxonomy ───────────────────────────────────────────────

const taxonomy: Builder = (profile) => {
  const scope = csrdScope(profile)
  const first = scopeRow('TAX-001', scope, profile, {
    above: {
      it: (who, size) => ({
        description: "Verifica dell'ambito dell'obbligo di informativa",
        article: 'art. 8, par. 1',
        gap: `${who} (${size}) è soggetta alla rendicontazione di sostenibilità e quindi all'informativa dell'articolo 8`,
      }),
      en: (who, size) => ({
        description: 'Scope check of the disclosure obligation',
        article: 'Art. 8(1)',
        gap: `${who} (${size}) is subject to sustainability reporting and therefore to the disclosure of Article 8`,
      }),
    },
    below: {
      it: (who, size) => ({
        description: 'Obbligo di informativa sulle attività ecosostenibili',
        article: 'art. 8, par. 1',
        gap: `${who} (${size}) non è soggetta alla rendicontazione di sostenibilità: l'informativa dell'articolo 8 non è dovuta`,
      }),
      en: (who, size) => ({
        description: 'Disclosure obligation on environmentally sustainable activities',
        article: 'Art. 8(1)',
        gap: `${who} (${size}) is not subject to sustainability reporting: the disclosure of Article 8 is not due`,
      }),
    },
    unknown: {
      it: () => ({
        description: "Ambito dell'obbligo di informativa",
        article: 'art. 8, par. 1',
        gap: "Da verificare: l'informativa è dovuta dalle imprese soggette alla rendicontazione di sostenibilità (più di 1.000 dipendenti e più di 450 milioni di euro di ricavi netti). Le righe seguenti descrivono un'impresa in ambito",
        effort: '1 settimana',
      }),
      en: () => ({
        description: 'Scope of the disclosure obligation',
        article: 'Art. 8(1)',
        gap: 'To be checked: the disclosure is due from undertakings subject to sustainability reporting (more than 1,000 employees and a net turnover above EUR 450 million). The following rows describe an undertaking in scope',
        effort: '1 week',
      }),
    },
  })

  if (scope === 'below') {
    return {
      score: 65,
      rows: [
        first,
        {
          id: 'TAX-002',
          status: 'IN_EVOLUTION',
          priority: 'P3',
          it: {
            description: 'Richieste di banche e clienti sulle attività ecosostenibili',
            article: 'art. 3',
            gap: 'Nessun obbligo di legge: rispondere è una scelta. I criteri che definiscono un\'attività ecosostenibile restano quelli dell\'articolo 3',
          },
          en: {
            description: 'Requests from banks and customers about environmentally sustainable activities',
            article: 'Art. 3',
            gap: 'No legal obligation: answering is a choice. The criteria that define an environmentally sustainable activity remain those of Article 3',
          },
        },
      ],
      recommendations: {
        it: [
          "Nessun obbligo diretto: se una banca chiede dati sulla Tassonomia, valuta con il cliente se e come rispondere.",
          'Rifai la verifica delle soglie a ogni chiusura di bilancio.',
        ],
        en: [
          'No direct obligation: if a bank asks for Taxonomy data, assess with the client whether and how to answer.',
          'Repeat the threshold check at every balance sheet date.',
        ],
      },
    }
  }

  return {
    score: 35,
    rows: [
      first,
      {
        id: 'TAX-002',
        status: 'NON_COMPLIANT',
        priority: 'P1',
        it: {
          description: 'Quota di fatturato da attività ecosostenibili',
          article: 'art. 8, par. 2, lett. a)',
          gap: 'Attività non ancora classificate: la quota non è calcolabile',
          effort: '6-8 settimane',
        },
        en: {
          description: 'Share of turnover from environmentally sustainable activities',
          article: 'Art. 8(2)(a)',
          gap: 'Activities not yet classified: the share cannot be calculated',
          effort: '6-8 weeks',
        },
      },
      {
        id: 'TAX-003',
        status: 'NON_COMPLIANT',
        priority: 'P1',
        it: {
          description: 'Quota di spese in conto capitale e di spese operative',
          article: 'art. 8, par. 2, lett. b)',
          gap: 'Dati contabili non ancora collegati alle attività',
          effort: '4-6 settimane',
        },
        en: {
          description: 'Share of capital expenditure and of operating expenditure',
          article: 'Art. 8(2)(b)',
          gap: 'Accounting data not yet linked to the activities',
          effort: '4-6 weeks',
        },
      },
      {
        id: 'TAX-004',
        status: 'PARTIALLY_COMPLIANT',
        priority: 'P2',
        it: {
          description: 'Contributo sostanziale e assenza di danno significativo',
          article: 'art. 3, lett. a) e b)',
          gap: 'Verifica svolta solo per lo stabilimento principale',
          effort: '4-5 settimane',
        },
        en: {
          description: 'Substantial contribution and no significant harm',
          article: 'Art. 3(a) and (b)',
          gap: 'Check carried out only for the main plant',
          effort: '4-5 weeks',
        },
      },
      {
        id: 'TAX-005',
        status: 'COMPLIANT',
        priority: 'P4',
        it: { description: 'Garanzie minime di salvaguardia', article: 'art. 18', evidence: 'Codice etico e procedura sui diritti umani' },
        en: { description: 'Minimum safeguards', article: 'Art. 18', evidence: 'Code of ethics and human rights procedure' },
      },
    ],
    recommendations: {
      it: [
        "Classifica le attività dell'impresa rispetto ai criteri di vaglio tecnico prima di calcolare le quote (art. 3).",
        'Collega fatturato, spese in conto capitale e spese operative alle attività classificate (art. 8, par. 2).',
        'Estendi la verifica del danno significativo a tutti gli stabilimenti.',
      ],
      en: [
        'Classify the activities of the company against the technical screening criteria before calculating the shares (Art. 3).',
        'Link turnover, capital expenditure and operating expenditure to the classified activities (Art. 8(2)).',
        'Extend the significant harm check to all plants.',
      ],
    },
  }
}

// ─── DORA ───────────────────────────────────────────────────

const dora: Builder = (profile) => {
  const scope = doraScope(profile)
  if (scope === 'below') {
    const who = { it: companyName(profile, 'it'), en: companyName(profile, 'en') }
    return {
      score: 65,
      rows: [
        {
          id: 'DORA-001',
          status: 'NOT_APPLICABLE',
          priority: 'P4',
          it: {
            description: 'Ambito di applicazione',
            article: 'art. 2',
            gap: `Il regolamento riguarda le entità finanziarie elencate all'articolo 2: ${who.it} opera in un altro settore e non ha obblighi diretti`,
          },
          en: {
            description: 'Scope',
            article: 'Art. 2',
            gap: `The regulation covers the financial entities listed in Article 2: ${who.en} operates in another sector and has no direct obligations`,
          },
        },
        {
          id: 'DORA-002',
          status: 'IN_EVOLUTION',
          priority: 'P3',
          it: {
            description: 'Clausole chieste dai clienti finanziari ai fornitori di servizi TIC',
            article: 'art. 30',
            gap: "Se l'impresa fornisce software o servizi TIC a banche o assicurazioni, i contratti devono contenere gli elementi dell'articolo 30",
          },
          en: {
            description: 'Clauses requested by financial customers from ICT service providers',
            article: 'Art. 30',
            gap: 'If the company supplies software or ICT services to banks or insurers, the contracts must contain the elements of Article 30',
          },
        },
      ],
      recommendations: {
        it: [
          "Nessun obbligo diretto: verifica se tra i clienti ci sono entità finanziarie.",
          "Se sì, confronta i contratti con gli elementi minimi dell'articolo 30 prima del rinnovo.",
        ],
        en: [
          'No direct obligation: check whether the customers include financial entities.',
          'If so, compare the contracts with the minimum elements of Article 30 before renewal.',
        ],
      },
    }
  }

  const first: Row =
    scope === 'above'
      ? {
          id: 'DORA-001',
          status: 'COMPLIANT',
          priority: 'P4',
          it: { description: "Verifica dell'ambito di applicazione", article: 'art. 2', gap: 'Entità finanziaria: regolamento in applicazione dal 17 gennaio 2025' },
          en: { description: 'Scope check', article: 'Art. 2', gap: 'Financial entity: regulation applicable since 17 January 2025' },
        }
      : {
          id: 'DORA-001',
          status: 'IN_EVOLUTION',
          priority: 'P1',
          it: {
            description: 'Ambito di applicazione',
            article: 'art. 2',
            gap: "Da verificare: il regolamento riguarda le entità finanziarie elencate all'articolo 2. Le righe seguenti descrivono un'entità finanziaria",
            effort: '1 settimana',
          },
          en: {
            description: 'Scope',
            article: 'Art. 2',
            gap: 'To be checked: the regulation covers the financial entities listed in Article 2. The following rows describe a financial entity',
            effort: '1 week',
          },
        }

  return {
    score: 52,
    rows: [
      first,
      {
        id: 'DORA-002',
        status: 'PARTIALLY_COMPLIANT',
        priority: 'P1',
        it: {
          description: 'Quadro per la gestione dei rischi informatici',
          article: 'art. 6',
          gap: 'Politica dei rischi informatici presente, non ancora riesaminata secondo il regolamento',
          effort: '4-6 settimane',
        },
        en: {
          description: 'ICT risk management framework',
          article: 'Art. 6',
          gap: 'An ICT risk policy exists but has not yet been reviewed against the regulation',
          effort: '4-6 weeks',
        },
      },
      {
        id: 'DORA-003',
        status: 'PARTIALLY_COMPLIANT',
        priority: 'P1',
        it: {
          description: 'Segnalazione dei gravi incidenti TIC',
          article: 'art. 19',
          gap: "Processo presente; modelli e termini delle norme tecniche non ancora adottati",
          effort: '3-4 settimane',
        },
        en: {
          description: 'Reporting of major ICT-related incidents',
          article: 'Art. 19',
          gap: 'A process exists; the templates and time limits of the technical standards have not been adopted yet',
          effort: '3-4 weeks',
        },
      },
      {
        id: 'DORA-004',
        status: 'NON_COMPLIANT',
        priority: 'P1',
        it: {
          description: 'Registro degli accordi con i fornitori terzi di servizi TIC',
          article: 'art. 28, par. 3',
          gap: 'Registro non ancora costituito',
          effort: '6-8 settimane',
        },
        en: {
          description: 'Register of the arrangements with ICT third-party service providers',
          article: 'Art. 28(3)',
          gap: 'Register not yet set up',
          effort: '6-8 weeks',
        },
      },
      {
        id: 'DORA-005',
        status: 'PARTIALLY_COMPLIANT',
        priority: 'P2',
        it: {
          description: 'Contenuto minimo dei contratti con i fornitori di servizi TIC',
          article: 'art. 30',
          gap: 'Clausole su audit e strategie di uscita assenti nei contratti più vecchi',
          effort: '6-8 settimane',
        },
        en: {
          description: 'Minimum content of the contracts with ICT service providers',
          article: 'Art. 30',
          gap: 'Audit and exit strategy clauses are missing from the older contracts',
          effort: '6-8 weeks',
        },
      },
      {
        id: 'DORA-006',
        status: 'COMPLIANT',
        priority: 'P4',
        it: { description: 'Politica di continuità operativa delle TIC', article: 'art. 11', evidence: 'Piano approvato e provato nel 2026' },
        en: { description: 'ICT business continuity policy', article: 'Art. 11', evidence: 'Plan approved and tested in 2026' },
      },
    ],
    recommendations: {
      it: [
        'Costituisci il registro degli accordi con i fornitori di servizi TIC (art. 28, par. 3).',
        "Adegua i contratti più vecchi al contenuto minimo dell'articolo 30, a partire dai servizi che supportano funzioni essenziali o importanti.",
        'Adotta modelli e termini delle norme tecniche per la segnalazione dei gravi incidenti (art. 19).',
        'Riesamina la politica dei rischi informatici rispetto agli articoli da 6 a 16.',
      ],
      en: [
        'Set up the register of the arrangements with ICT service providers (Art. 28(3)).',
        'Bring the older contracts up to the minimum content of Article 30, starting from the services that support critical or important functions.',
        'Adopt the templates and time limits of the technical standards for reporting major incidents (Art. 19).',
        'Review the ICT risk policy against Articles 6 to 16.',
      ],
    },
  }
}

const BUILDERS: Record<string, Builder> = {
  CSRD: csrd,
  CSDDD: csddd,
  AI_ACT: aiAct,
  DORA: dora,
  NIS2: nis2,
  TAXONOMY: taxonomy,
  GDPR: gdpr,
  CRA: cra,
}

/**
 * The demo gap analysis of one framework. `profile` is the company the
 * analysis is about (the API client can pass the `company_profile` of the
 * request); `language` defaults to the interface language.
 */
export function getMockGapAnalysis(
  framework: string,
  profile?: DemoProfile,
  language: Language = demoLanguage(),
): GapAnalysisResponse {
  const analysis = (BUILDERS[framework] ?? BUILDERS.GDPR)(profile)

  const requirements: Requirement[] = analysis.rows.map((row) => {
    const text = row[language]
    return {
      requirement_id: row.id,
      description: text.description,
      article_reference: text.article,
      status: row.status,
      evidence: text.evidence ?? '',
      gap_description: text.gap ?? '',
      remediation_effort: text.effort ?? '',
      priority: row.priority,
      notes: '',
    }
  })

  const status_summary = { compliant: 0, partially_compliant: 0, non_compliant: 0, not_applicable: 0, in_evolution: 0 }
  for (const r of requirements) {
    if (r.status === 'COMPLIANT') status_summary.compliant++
    else if (r.status === 'PARTIALLY_COMPLIANT') status_summary.partially_compliant++
    else if (r.status === 'NON_COMPLIANT') status_summary.non_compliant++
    else if (r.status === 'NOT_APPLICABLE') status_summary.not_applicable++
    else status_summary.in_evolution++
  }

  return {
    framework,
    overall_score: analysis.score,
    status_summary,
    requirements,
    top_recommendations: analysis.recommendations[language],
    // A fixed, medium confidence: sample findings, to be read as a preliminary estimate.
    confidence_score: 0.75,
    requires_expert_review: true,
  }
}
