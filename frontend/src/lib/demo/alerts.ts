/**
 * The alerts of the demo, as they stood on the demo date (acts.ts). Dates
 * are fixed: an alert never claims to be "of yesterday", and a deadline that
 * has passed is shown as passed. Every date and reference was read on the
 * official text (EUR-Lex, Normattiva) on 2026-11-11; `source` names it.
 */
import type { Language } from '@/i18n/config'
import type { Severity } from '../types'
import { localized } from './language'

interface AlertText {
  title: string
  description: string
  actions_required: string[]
  source: string
}

interface AlertRecord {
  id: string
  severity: Severity
  framework: string
  client_id: string | null
  is_read: boolean
  created_at: string
  deadline: string | null
  text: Record<Language, AlertText>
}

const ALERTS: AlertRecord[] = [
  {
    id: '1',
    severity: 'CRITICAL',
    framework: 'AI_ACT',
    client_id: 'demo-c2',
    is_read: false,
    created_at: '2026-11-02T08:00:00Z',
    deadline: '2026-12-02',
    text: {
      it: {
        title: 'AI Act: marcatura dei contenuti generati entro il 2 dicembre 2026',
        description:
          "Chi fornisce un sistema di IA che genera testi, immagini, audio o video, già sul mercato prima del 2 agosto 2026, deve adeguarsi all'articolo 50, paragrafo 2, entro il 2 dicembre 2026: gli output vanno marcati in un formato leggibile meccanicamente. Riguarda l'assistente di scrittura di Beta Software.",
        actions_required: [
          'Elencare le funzioni che generano contenuti',
          'Verificare con il fornitore del modello quale marcatura è disponibile',
          'Documentare la soluzione adottata',
        ],
        source: 'Regolamento (UE) 2024/1689, art. 50, par. 2, e art. 111, par. 4 (testo consolidato al 27 luglio 2026)',
      },
      en: {
        title: 'AI Act: marking of generated content by 2 December 2026',
        description:
          'A provider of an AI system that generates text, images, audio or video, already on the market before 2 August 2026, must comply with Article 50(2) by 2 December 2026: the outputs have to be marked in a machine-readable format. This concerns the writing assistant of Beta Software.',
        actions_required: [
          'List the functions that generate content',
          'Check with the model provider which marking is available',
          'Document the solution adopted',
        ],
        source: 'Regulation (EU) 2024/1689, Art. 50(2) and Art. 111(4) (consolidated text of 27 July 2026)',
      },
    },
  },
  {
    id: '2',
    severity: 'HIGH',
    framework: 'CSRD',
    client_id: null,
    is_read: false,
    created_at: '2026-10-26T08:00:00Z',
    deadline: '2026-12-22',
    text: {
      it: {
        title: 'CSRD in Italia: il D.L. 193/2026 esclude le imprese sotto soglia per gli esercizi 2026 e 2027',
        description:
          "Il decreto-legge 23 ottobre 2026, n. 193 ha aggiunto il comma 3-bis all'articolo 17 del D.Lgs. 125/2024: per gli esercizi che iniziano tra il 1° gennaio 2026 e il 31 dicembre 2027 il decreto non si applica alle imprese con ricavi netti non superiori a 450 milioni di euro o con non più di 1.000 dipendenti. È un decreto-legge: decade se non è convertito entro sessanta giorni dalla pubblicazione, cioè entro il 22 dicembre 2026.",
        actions_required: [
          'Individuare i clienti che stavano preparando la rendicontazione per il 2026',
          'Seguire la legge di conversione e rileggere il testo quando esce',
        ],
        source: 'Normattiva: D.L. 23 ottobre 2026, n. 193, art. 10; Costituzione, art. 77',
      },
      en: {
        title: 'CSRD in Italy: Decree-Law 193/2026 excludes companies below the thresholds for financial years 2026 and 2027',
        description:
          'Decree-Law No 193 of 23 October 2026 added paragraph 3-bis to Article 17 of Legislative Decree 125/2024: for financial years starting between 1 January 2026 and 31 December 2027 the decree does not apply to undertakings with a net turnover not above EUR 450 million or with no more than 1,000 employees. It is a decree-law: it lapses unless converted into law within sixty days of publication, that is by 22 December 2026.',
        actions_required: [
          'Identify the clients that were preparing their report for 2026',
          'Follow the conversion law and read the text again when it is published',
        ],
        source: 'Normattiva: Decree-Law No 193 of 23 October 2026, Art. 10; Italian Constitution, Art. 77',
      },
    },
  },
  {
    id: '3',
    severity: 'MEDIUM',
    framework: 'NIS2',
    client_id: null,
    is_read: false,
    created_at: '2026-11-04T08:00:00Z',
    deadline: '2027-02-28',
    text: {
      it: {
        title: 'NIS2: registrazione annuale sulla piattaforma ACN dal 1° gennaio al 28 febbraio 2027',
        description:
          "I soggetti che rientrano nel D.Lgs. 138/2024 si registrano o aggiornano la registrazione sulla piattaforma dell'Agenzia per la cybersicurezza nazionale dal 1° gennaio al 28 febbraio di ogni anno. Tra i clienti dello studio riguarda le imprese di settori degli allegati che superano i massimali delle piccole imprese: Alfa Macchine Utensili, Gamma Alimentari, Delta Corriere Espresso e Zeta Componenti.",
        actions_required: [
          'Confermare per ogni cliente settore e dimensione',
          'Verificare punto di contatto e recapiti da comunicare',
        ],
        source: 'Normattiva: D.Lgs. 4 settembre 2024, n. 138, art. 3 e art. 7, comma 1',
      },
      en: {
        title: 'NIS2: yearly registration on the ACN platform from 1 January to 28 February 2027',
        description:
          'Entities covered by Legislative Decree 138/2024 register or update their registration on the platform of the National Cybersecurity Agency from 1 January to 28 February of each year. Among the clients of the firm it concerns the companies in the sectors of the annexes that exceed the ceilings for small enterprises: Alfa Macchine Utensili, Gamma Alimentari, Delta Corriere Espresso and Zeta Componenti.',
        actions_required: [
          'Confirm sector and size for each client',
          'Check the contact point and the details to be communicated',
        ],
        source: 'Normattiva: Legislative Decree No 138 of 4 September 2024, Art. 3 and Art. 7(1)',
      },
    },
  },
  {
    id: '4',
    severity: 'LOW',
    framework: 'CSRD',
    client_id: 'demo-c6',
    is_read: false,
    created_at: '2026-11-10T08:00:00Z',
    deadline: null,
    text: {
      it: {
        title: 'CSRD: i principi ESRS rivisti sono in vigore dal 10 novembre 2026',
        description:
          "Il Regolamento delegato (UE) 2026/1563 sostituisce gli allegati del Regolamento delegato (UE) 2023/2772 e si applica agli esercizi che iniziano dal 1° gennaio 2027. Per l'esercizio 2026 chi già rendiconta può scegliere tra la versione precedente e quella nuova, indicando quale applica. Riguarda Zeta Componenti, unico cliente sopra entrambe le soglie.",
        actions_required: ["Decidere con il cliente quale versione applicare per l'esercizio 2026"],
        source: 'Regolamento delegato (UE) 2026/1563, art. 2 e art. 3',
      },
      en: {
        title: 'CSRD: the revised ESRS are in force since 10 November 2026',
        description:
          'Delegated Regulation (EU) 2026/1563 replaces the annexes of Delegated Regulation (EU) 2023/2772 and applies to financial years starting on or after 1 January 2027. For financial year 2026 undertakings that already report may choose between the previous version and the new one, stating which one they apply. This concerns Zeta Componenti, the only client above both thresholds.',
        actions_required: ['Decide with the client which version to apply for financial year 2026'],
        source: 'Delegated Regulation (EU) 2026/1563, Art. 2 and Art. 3',
      },
    },
  },
  {
    id: '5',
    severity: 'MEDIUM',
    framework: 'AI_ACT',
    client_id: 'demo-c5',
    is_read: true,
    created_at: '2026-07-28T08:00:00Z',
    deadline: null,
    text: {
      it: {
        title: "AI Act: l'articolo 4 sull'alfabetizzazione è stato sostituito",
        description:
          "Il Regolamento (UE) 2026/1744, in vigore dal 27 luglio 2026, ha riscritto l'articolo 4: fornitori e deployer adottano misure per sostenere l'alfabetizzazione in materia di IA, senza dover garantire un livello specifico per alcuna persona. La policy sull'uso dell'IA di Epsilon Salute cita il testo precedente.",
        actions_required: ["Aggiornare il riferimento all'articolo 4 nella policy interna"],
        source: 'Regolamento (UE) 2024/1689, art. 4 (testo consolidato al 27 luglio 2026)',
      },
      en: {
        title: 'AI Act: Article 4 on AI literacy has been replaced',
        description:
          'Regulation (EU) 2026/1744, in force since 27 July 2026, rewrote Article 4: providers and deployers take measures to support AI literacy, without having to guarantee a specific level for any individual. The AI use policy of Epsilon Salute quotes the previous text.',
        actions_required: ['Update the reference to Article 4 in the internal policy'],
        source: 'Regulation (EU) 2024/1689, Art. 4 (consolidated text of 27 July 2026)',
      },
    },
  },
  {
    id: '6',
    severity: 'INFORMATIONAL',
    framework: 'CRA',
    client_id: 'demo-c1',
    is_read: true,
    created_at: '2026-09-14T08:00:00Z',
    deadline: '2027-12-11',
    text: {
      it: {
        title: "CRA: segnalazione delle vulnerabilità sfruttate già obbligatoria, piena applicazione dall'11 dicembre 2027",
        description:
          "Dall'11 settembre 2026 i fabbricanti di prodotti con elementi digitali notificano le vulnerabilità attivamente sfruttate e gli incidenti gravi: preallarme entro 24 ore, notifica entro 72 ore. Il resto del regolamento si applica dall'11 dicembre 2027. Riguarda i controlli numerici di Alfa Macchine Utensili.",
        actions_required: ['Definire chi riceve le segnalazioni e chi notifica', "Pianificare l'adeguamento dei prodotti entro il 2027"],
        source: 'Regolamento (UE) 2024/2847, art. 14 e art. 71',
      },
      en: {
        title: 'CRA: reporting of exploited vulnerabilities already mandatory, full application from 11 December 2027',
        description:
          'Since 11 September 2026 manufacturers of products with digital elements notify actively exploited vulnerabilities and severe incidents: early warning within 24 hours, notification within 72 hours. The rest of the regulation applies from 11 December 2027. This concerns the numerical controls of Alfa Macchine Utensili.',
        actions_required: ['Define who receives the reports and who notifies', 'Plan the adaptation of the products by 2027'],
        source: 'Regulation (EU) 2024/2847, Art. 14 and Art. 71',
      },
    },
  },
]

/** An alert in the shape GET /api/v1/alerts returns, in one language. */
function alertIn(language: Language, { text, ...record }: AlertRecord) {
  return { ...record, regulation_id: null, is_dismissed: false, ...text[language] }
}

/** The alerts in a given language (plain objects). */
export function getDemoAlerts(language: Language) {
  return ALERTS.map((record) => alertIn(language, record))
}

/**
 * The same alerts as one constant, for the API client: title, description,
 * actions and source follow the interface language when they are read.
 */
export const DEMO_ALERTS = ALERTS.map((record) =>
  localized({ it: alertIn('it', record), en: alertIn('en', record) }),
)

function countBy(key: 'severity' | 'framework'): Record<string, number> {
  const counts: Record<string, number> = {}
  for (const alert of ALERTS) counts[alert[key]] = (counts[alert[key]] ?? 0) + 1
  return counts
}

export const DEMO_ALERT_SUMMARY = {
  total: ALERTS.length,
  unread: ALERTS.filter((a) => !a.is_read).length,
  by_severity: countBy('severity'),
  by_framework: countBy('framework'),
}
