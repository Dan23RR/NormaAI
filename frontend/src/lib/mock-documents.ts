/**
 * Canned data of the declared demo ("Demo con dati di esempio") for Controlla,
 * and the demo answers of the documents API (prefix /api/v1/documents).
 *
 * The four checks below were not written by hand. On 11 November 2026 four
 * invented documents went through the document check (src/document_check)
 * against the texts CELLAR serves, and the result through the serialisation
 * of the documents API (src/document_check/serialize.py): what is here is
 * what the API answers, field for field. So every official passage
 * (`official_quote`, `before.text`, `after_text`) is the literal official
 * text of the version named next to it, and every outcome is one the product
 * really gives:
 *
 * - a procedure that quotes article 33(1) GDPR with "48 ore" where the
 *   regulation says "72 ore", cites a paragraph that does not exist and puts
 *   a quote under the wrong article;
 * - an AI policy of 15 March 2026 that quotes article 4 of the AI Act as it
 *   was before Regulation (EU) 2026/1744 replaced it (consolidated text of
 *   27 July 2026), with the article then and now;
 * - an English clause checked without surveillance and without a client;
 * - a note to suppliers checked on 16 February 2026 against the CSDDD as
 *   consolidated on 17 April 2025, when everything in it was right. The
 *   re-check then found articles 2, 10 and 37 changed in the consolidated
 *   text of 18 March 2026 (Directive (EU) 2026/470): the check is "da
 *   rivedere" and its references to those articles moved under "correggere",
 *   each with the article then and now.
 *
 * The documents, the clients and the dates of the checks and re-checks are
 * invented; nothing here is a real client document. To make the data again
 * after the engine changes, run the same documents through `check_text`,
 * `serialize.findings_to_json` and `serialize.effective_findings`.
 */
import type { CheckList, CheckSummary, DocumentCheck, DocumentPreferences, Finding, FindingGroup } from '@/components/controlla/types'
import { ApiError } from './api-error'
import { diffWords } from './word-diff'

// ─── The four checks ─────────────────────────────────────────

export const DEMO_DOCUMENTS: DocumentCheck[] = [
  {
    id: 'demo-doc-gdpr',
    client_id: 'demo-c2',
    filename: 'Procedura violazioni dati personali.docx',
    document_sha256: 'e32da5ea5e4f56907b36a32aed8eff3c87c56171cd2d55dc148d2063a9e6521a',
    document_date: '2026-01-12',
    checked_at: '2026-11-10T09:42:00Z',
    lang: 'IT',
    watch: true,
    status: 'correggere',
    needs_review: false,
    counts: { correggere: 2, controllare: 1, a_posto: 4, non_coperto: 1 },
    findings: [
      {
        id: 'f1',
        group: 'correggere',
        status: { code: 'alterata', label: 'Citazione diversa dal testo ufficiale' },
        line: 8,
        raw: 'articolo 33, paragrafo 1, del regolamento (UE) 2016/679',
        context: "Ai sensi dell'articolo 33, paragrafo 1, del regolamento (UE) 2016/679, la banca notifica la violazione al Garante «senza ingiustificato ritardo e, ove ...",
        act: { source: 'eurlex', id: '32016R0679', name: 'GDPR', label: 'regolamento (UE) 2016/679 (GDPR)' },
        provision: {
          key: 'art:33',
          label: 'art. 33, par. 1',
          paragraphs: ['1'],
        },
        version: { id: '02016R0679-20160504', as_of: '2016-05-04', label: 'testo consolidato al 04/05/2016' },
        url: 'https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:02016R0679-20160504',
        messages: [
          'Art. 33, par. 1 esiste nel testo consolidato al 04/05/2016.',
          'La citazione è diversa dal testo vigente: nel documento «48», nel testo ufficiale «72».',
        ],
        quotes: [
          'senza ingiustificato ritardo e, ove possibile, entro 48 ore dal momento in cui ne è venuto a conoscenza',
        ],
        official_quote: 'senza ingiustificato ritardo e, ove possibile, entro 72 ore dal momento in cui ne è venuto a conoscenza',
        altered_quote: 'senza ingiustificato ritardo e, ove possibile, entro 48 ore dal momento in cui ne è venuto a conoscenza',
        differences: [{ quoted: '48', official: '72' }],
        before: null,
        after_text: null,
        dependency: { source: 'eurlex', act: '32016R0679', key: 'art:33' },
      },
      {
        id: 'f2',
        group: 'a_posto',
        status: { code: 'valido', label: 'Riferimento valido' },
        line: 11,
        raw: 'art. 33, par. 3, del GDPR',
        context: "La notifica contiene almeno gli elementi elencati dall'art. 33, par. 3, del GDPR.",
        act: { source: 'eurlex', id: '32016R0679', name: 'GDPR', label: 'GDPR' },
        provision: {
          key: 'art:33',
          label: 'art. 33, par. 3',
          paragraphs: ['3'],
        },
        version: { id: '02016R0679-20160504', as_of: '2016-05-04', label: 'testo consolidato al 04/05/2016' },
        url: 'https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:02016R0679-20160504',
        messages: ['Art. 33, par. 3 esiste nel testo consolidato al 04/05/2016.'],
        quotes: [],
        official_quote: null,
        altered_quote: null,
        differences: [],
        before: null,
        after_text: null,
        dependency: { source: 'eurlex', act: '32016R0679', key: 'art:33' },
      },
      {
        id: 'f3',
        group: 'a_posto',
        status: { code: 'verificata', label: 'Citazione verificata' },
        line: 14,
        raw: 'art. 34, par. 1, del GDPR',
        context: "L'art. 34, par. 1, del GDPR prevede che «il titolare del trattamento comunica la violazione all'interessato senza ingiustificato ritardo».",
        act: { source: 'eurlex', id: '32016R0679', name: 'GDPR', label: 'GDPR' },
        provision: {
          key: 'art:34',
          label: 'art. 34, par. 1',
          paragraphs: ['1'],
        },
        version: { id: '02016R0679-20160504', as_of: '2016-05-04', label: 'testo consolidato al 04/05/2016' },
        url: 'https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:02016R0679-20160504',
        messages: [
          'Art. 34, par. 1 esiste nel testo consolidato al 04/05/2016.',
          'La citazione è nel testo vigente, parola per parola.',
        ],
        quotes: [
          "il titolare del trattamento comunica la violazione all'interessato senza ingiustificato ritardo",
        ],
        official_quote: "il titolare del trattamento comunica la violazione all'interessato senza ingiustificato ritardo",
        altered_quote: null,
        differences: [],
        before: null,
        after_text: null,
        dependency: { source: 'eurlex', act: '32016R0679', key: 'art:34' },
      },
      {
        id: 'f4',
        group: 'controllare',
        status: { code: 'altro_articolo', label: 'Citazione in un altro articolo' },
        line: 17,
        raw: 'art. 28, par. 3, del GDPR',
        context: "In base all'art. 28, par. 3, del GDPR, il fornitore che tratta dati per conto della banca «informa il titolare del trattamento senza ingiustificato ...",
        act: { source: 'eurlex', id: '32016R0679', name: 'GDPR', label: 'GDPR' },
        provision: {
          key: 'art:28',
          label: 'art. 28, par. 3',
          paragraphs: ['3'],
        },
        version: { id: '02016R0679-20160504', as_of: '2016-05-04', label: 'testo consolidato al 04/05/2016' },
        url: 'https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:02016R0679-20160504',
        messages: [
          'Art. 28, par. 3 esiste nel testo consolidato al 04/05/2016.',
          'La citazione è nel testo vigente, ma in Art. 33, non nella disposizione citata.',
        ],
        quotes: [
          'informa il titolare del trattamento senza ingiustificato ritardo dopo essere venuto a conoscenza della violazione',
        ],
        official_quote: 'informa il titolare del trattamento senza ingiustificato ritardo dopo essere venuto a conoscenza della violazione',
        altered_quote: null,
        differences: [],
        before: null,
        after_text: null,
        dependency: { source: 'eurlex', act: '32016R0679', key: 'art:28' },
      },
      {
        id: 'f5',
        group: 'a_posto',
        status: { code: 'verificata', label: 'Citazione verificata' },
        line: 20,
        raw: 'art. 33, par. 5, del GDPR',
        context: "Come richiede l'art. 33, par. 5, del GDPR, «Il titolare del trattamento documenta qualsiasi violazione dei dati personali, comprese le circostanze a ...",
        act: { source: 'eurlex', id: '32016R0679', name: 'GDPR', label: 'GDPR' },
        provision: {
          key: 'art:33',
          label: 'art. 33, par. 5',
          paragraphs: ['5'],
        },
        version: { id: '02016R0679-20160504', as_of: '2016-05-04', label: 'testo consolidato al 04/05/2016' },
        url: 'https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:02016R0679-20160504',
        messages: [
          'Art. 33, par. 5 esiste nel testo consolidato al 04/05/2016.',
          'La citazione è nel testo vigente, parola per parola.',
        ],
        quotes: [
          'Il titolare del trattamento documenta qualsiasi violazione dei dati personali, comprese le circostanze a essa relative, le sue conseguenze e i provvedimenti adottati per porvi rimedio',
        ],
        official_quote: 'Il titolare del trattamento documenta qualsiasi violazione dei dati personali, comprese le circostanze a essa relative, le sue conseguenze e i provvedimenti adottati per porvi rimedio',
        altered_quote: null,
        differences: [],
        before: null,
        after_text: null,
        dependency: { source: 'eurlex', act: '32016R0679', key: 'art:33' },
      },
      {
        id: 'f6',
        group: 'correggere',
        status: { code: 'inesistente', label: 'Non esiste nel testo vigente' },
        line: 23,
        raw: 'art. 33, par. 6, del GDPR',
        context: "Per i tempi di conservazione del registro si applica l'art. 33, par. 6, del GDPR.",
        act: { source: 'eurlex', id: '32016R0679', name: 'GDPR', label: 'GDPR' },
        provision: {
          key: 'art:33',
          label: 'art. 33, par. 6',
          paragraphs: ['6'],
        },
        version: { id: '02016R0679-20160504', as_of: '2016-05-04', label: 'testo consolidato al 04/05/2016' },
        url: 'https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:02016R0679-20160504',
        messages: [
          "Il paragrafo 6 non esiste nel testo consolidato al 04/05/2016: l'art. 33 ha i paragrafi da 1 a 5.",
        ],
        quotes: [],
        official_quote: null,
        altered_quote: null,
        differences: [],
        before: null,
        after_text: null,
        dependency: { source: 'eurlex', act: '32016R0679', key: 'art:33' },
      },
      {
        id: 'f7',
        group: 'a_posto',
        status: { code: 'valido', label: 'Riferimento valido' },
        line: 26,
        raw: 'art. 83, par. 4, del GDPR',
        context: "La mancata notifica espone alle sanzioni dell'art. 83, par. 4, del GDPR.",
        act: { source: 'eurlex', id: '32016R0679', name: 'GDPR', label: 'GDPR' },
        provision: {
          key: 'art:83',
          label: 'art. 83, par. 4',
          paragraphs: ['4'],
        },
        version: { id: '02016R0679-20160504', as_of: '2016-05-04', label: 'testo consolidato al 04/05/2016' },
        url: 'https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:02016R0679-20160504',
        messages: ['Art. 83, par. 4 esiste nel testo consolidato al 04/05/2016.'],
        quotes: [],
        official_quote: null,
        altered_quote: null,
        differences: [],
        before: null,
        after_text: null,
        dependency: { source: 'eurlex', act: '32016R0679', key: 'art:83' },
      },
      {
        id: 'f8',
        group: 'non_coperto',
        status: { code: 'non_coperto', label: 'Diritto italiano, non ancora coperto' },
        line: 29,
        raw: 'art. 154 del d.lgs. 196/2003',
        context: "Restano fermi i compiti del Garante previsti dall'art. 154 del d.lgs. 196/2003.",
        act: {
          source: 'normattiva',
          id: 'IT:dlgs:2003:196',
          name: 'D.Lgs. 196/2003 (Codice privacy)',
          label: 'D.Lgs. 196/2003 (Codice privacy)',
        },
        provision: { key: 'art:154', label: 'art. 154', paragraphs: [] },
        version: null,
        url: 'https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2003;196',
        messages: [
          'NormaAI non ha ancora i testi italiani: da controllare su Normattiva.',
        ],
        quotes: [],
        official_quote: null,
        altered_quote: null,
        differences: [],
        before: null,
        after_text: null,
        dependency: null,
      },
    ],
    dependencies: [
      {
        source: 'eurlex',
        act: '32016R0679',
        name: 'GDPR',
        article: 'Art. 33',
        key: 'art:33',
        version: '02016R0679-20160504',
        as_of: '2016-05-04',
        fingerprint: 'sha256:ad60a05f01f6a1cbd9012053cb06101df04e3e3784f8bcef3cc245cb364701f2',
        state: 'current',
        changed_at: null,
        lang: 'IT',
        cited_as: [
          'articolo 33, paragrafo 1, del regolamento (UE) 2016/679',
          'art. 33, par. 3, del GDPR',
          'art. 33, par. 5, del GDPR',
          'art. 33, par. 6, del GDPR',
        ],
        checked_at: '2026-11-10T09:42:00Z',
        message: null,
        current_version: null,
        current_as_of: null,
      },
      {
        source: 'eurlex',
        act: '32016R0679',
        name: 'GDPR',
        article: 'Art. 34',
        key: 'art:34',
        version: '02016R0679-20160504',
        as_of: '2016-05-04',
        fingerprint: 'sha256:393bec92e11bdf6ada7bae40f62783bf625e5ac7b9bb6dc37162814e465ddca8',
        state: 'current',
        changed_at: null,
        lang: 'IT',
        cited_as: ['art. 34, par. 1, del GDPR'],
        checked_at: '2026-11-10T09:42:00Z',
        message: null,
        current_version: null,
        current_as_of: null,
      },
      {
        source: 'eurlex',
        act: '32016R0679',
        name: 'GDPR',
        article: 'Art. 28',
        key: 'art:28',
        version: '02016R0679-20160504',
        as_of: '2016-05-04',
        fingerprint: 'sha256:9d72e504bffd3981a19ddc9653c4fdaaaaf24ba0515b06254fede1ea31a8d466',
        state: 'current',
        changed_at: null,
        lang: 'IT',
        cited_as: ['art. 28, par. 3, del GDPR'],
        checked_at: '2026-11-10T09:42:00Z',
        message: null,
        current_version: null,
        current_as_of: null,
      },
      {
        source: 'eurlex',
        act: '32016R0679',
        name: 'GDPR',
        article: 'Art. 83',
        key: 'art:83',
        version: '02016R0679-20160504',
        as_of: '2016-05-04',
        fingerprint: 'sha256:313abd03b1acb322f99e8ca258d6837bd01eb459cbc4d0b207cdde6272087dd6',
        state: 'current',
        changed_at: null,
        lang: 'IT',
        cited_as: ['art. 83, par. 4, del GDPR'],
        checked_at: '2026-11-10T09:42:00Z',
        message: null,
        current_version: null,
        current_as_of: null,
      },
    ],
    rechecked_at: null,
  },
  {
    id: 'demo-doc-ai',
    client_id: 'demo-c3',
    filename: 'Policy uso IA.pdf',
    document_sha256: 'f5b37bab3e7c9ac543574d2ab4f2a2d8ff197c5c83b7d9df12fe575742a72428',
    document_date: '2026-03-15',
    checked_at: '2026-11-04T15:08:00Z',
    lang: 'IT',
    watch: true,
    status: 'correggere',
    needs_review: false,
    counts: { correggere: 1, controllare: 0, a_posto: 3, non_coperto: 0 },
    findings: [
      {
        id: 'f1',
        group: 'correggere',
        status: { code: 'superata', label: 'Citazione superata' },
        line: 5,
        raw: 'articolo 4 del regolamento (UE) 2024/1689',
        context: "L'articolo 4 del regolamento (UE) 2024/1689 (di seguito «AI Act») dispone: «I fornitori e i deployer dei sistemi di IA adottano misure per garantire ...",
        act: { source: 'eurlex', id: '32024R1689', name: 'AI Act', label: 'regolamento (UE) 2024/1689 (AI Act)' },
        provision: { key: 'art:4', label: 'art. 4', paragraphs: [] },
        version: { id: '02024R1689-20260727', as_of: '2026-07-27', label: 'testo consolidato al 27/07/2026' },
        url: 'https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:02024R1689-20260727',
        messages: [
          'Art. 4 esiste nel testo consolidato al 27/07/2026.',
          'Art. 4 è cambiato dopo la data del documento (15/03/2026): il documento si basa sul testo originale, oggi vale il testo consolidato al 27/07/2026.',
          'La citazione corrisponde al testo originale, in vigore fino al 26/07/2026, non al testo vigente: la disposizione è cambiata.',
        ],
        quotes: [
          'I fornitori e i deployer dei sistemi di IA adottano misure per garantire nella misura del possibile un livello sufficiente di alfabetizzazione in materia di IA del loro personale',
        ],
        official_quote: null,
        altered_quote: null,
        differences: [],
        before: {
          version_label: 'testo originale',
          version_id: '32024R1689',
          as_of: null,
          text: "Articolo 4\nAlfabetizzazione in materia di IA\nI fornitori e i deployer dei sistemi di IA adottano misure per garantire nella misura del possibile un livello sufficiente di alfabetizzazione in materia di IA del loro personale nonché di qualsiasi altra persona che si occupa del funzionamento e dell'utilizzo dei sistemi di IA per loro conto, prendendo in considerazione le loro conoscenze tecniche, la loro esperienza, istruzione e formazione, nonché il contesto in cui i sistemi di IA devono essere utilizzati, e tenendo conto delle persone o dei gruppi di persone su cui i sistemi di IA devono essere utilizzati.",
        },
        after_text: "Articolo 4\nAlfabetizzazione in materia di IA\n1. I fornitori e i deployer di sistemi di IA adottano misure volte a sostenere lo sviluppo dell'alfabetizzazione in materia di IA del loro personale nonché di qualsiasi altra persona che si occupa del funzionamento e dell'utilizzo dei sistemi di IA per loro conto, prendendo in considerazione le loro conoscenze tecniche, la loro esperienza, istruzione e formazione, nonché il contesto in cui i sistemi di IA devono essere utilizzati, e tenendo conto delle persone o dei gruppi di persone su cui i sistemi di IA devono essere utilizzati. Tale obbligo non impone ai fornitori o ai deployer di garantire un livello specifico di alfabetizzazione in materia di IA per alcuna persona.\n2. La Commissione e gli Stati membri sostengono e agevolano gli sforzi dei fornitori e dei deployer di sistemi di IA, in particolare delle PMI, nell'adempimento dell'obbligo di cui al paragrafo 1 del presente articolo. A tal fine, la Commissione pubblica esempi pratici di come adempiere a tale obbligo sulla piattaforma unica di informazione di cui all'articolo 62, paragrafo 3, lettera b).\n3. Il consiglio per l'IA adotta raccomandazioni, tenendo conto dei quadri europei delle competenze, per sostenere la Commissione e gli Stati membri nella promozione dell'alfabetizzazione in materia di IA richiesta a norma del paragrafo 1, anche stabilendo obiettivi comuni.",
        dependency: { source: 'eurlex', act: '32024R1689', key: 'art:4' },
      },
      {
        id: 'f2',
        group: 'a_posto',
        status: { code: 'verificata', label: 'Citazione verificata' },
        line: 8,
        raw: "art. 50, par. 1, dell'AI Act",
        context: "Gli assistenti virtuali rispettano l'art. 50, par. 1, dell'AI Act: le persone devono essere «informate del fatto di stare interagendo con un sistema di IA».",
        act: { source: 'eurlex', id: '32024R1689', name: 'AI Act', label: 'AI Act' },
        provision: {
          key: 'art:50',
          label: 'art. 50, par. 1',
          paragraphs: ['1'],
        },
        version: { id: '02024R1689-20260727', as_of: '2026-07-27', label: 'testo consolidato al 27/07/2026' },
        url: 'https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:02024R1689-20260727',
        messages: [
          'Art. 50, par. 1 esiste nel testo consolidato al 27/07/2026.',
          'Art. 50 è cambiato dopo la data del documento (15/03/2026), ma non nella parte citata.',
          'La citazione è nel testo vigente, parola per parola.',
        ],
        quotes: [
          'informate del fatto di stare interagendo con un sistema di IA',
        ],
        official_quote: 'informate del fatto di stare interagendo con un sistema di IA',
        altered_quote: null,
        differences: [],
        before: null,
        after_text: null,
        dependency: { source: 'eurlex', act: '32024R1689', key: 'art:50' },
      },
      {
        id: 'f3',
        group: 'a_posto',
        status: { code: 'verificata', label: 'Citazione verificata' },
        line: 11,
        raw: "art. 26, par. 2, dell'AI Act",
        context: "Per i sistemi ad alto rischio si applica l'art. 26, par. 2, dell'AI Act: «I deployer affidano la sorveglianza umana a persone fisiche che dispongono ...",
        act: { source: 'eurlex', id: '32024R1689', name: 'AI Act', label: 'AI Act' },
        provision: {
          key: 'art:26',
          label: 'art. 26, par. 2',
          paragraphs: ['2'],
        },
        version: { id: '02024R1689-20260727', as_of: '2026-07-27', label: 'testo consolidato al 27/07/2026' },
        url: 'https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:02024R1689-20260727',
        messages: [
          'Art. 26, par. 2 esiste nel testo consolidato al 27/07/2026.',
          'La citazione è nel testo vigente, parola per parola.',
        ],
        quotes: [
          "I deployer affidano la sorveglianza umana a persone fisiche che dispongono della competenza, della formazione e dell'autorità necessarie nonché del sostegno necessario",
        ],
        official_quote: "I deployer affidano la sorveglianza umana a persone fisiche che dispongono della competenza, della formazione e dell'autorità necessarie nonché del sostegno necessario",
        altered_quote: null,
        differences: [],
        before: null,
        after_text: null,
        dependency: { source: 'eurlex', act: '32024R1689', key: 'art:26' },
      },
      {
        id: 'f4',
        group: 'a_posto',
        status: { code: 'valido', label: 'Riferimento valido' },
        line: 14,
        raw: 'art. 9 del GDPR',
        context: "Il trattamento dei dati relativi alla salute segue l'art. 9 del GDPR.",
        act: { source: 'eurlex', id: '32016R0679', name: 'GDPR', label: 'GDPR' },
        provision: { key: 'art:9', label: 'art. 9', paragraphs: [] },
        version: { id: '02016R0679-20160504', as_of: '2016-05-04', label: 'testo consolidato al 04/05/2016' },
        url: 'https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:02016R0679-20160504',
        messages: ['Art. 9 esiste nel testo consolidato al 04/05/2016.'],
        quotes: [],
        official_quote: null,
        altered_quote: null,
        differences: [],
        before: null,
        after_text: null,
        dependency: { source: 'eurlex', act: '32016R0679', key: 'art:9' },
      },
    ],
    dependencies: [
      {
        source: 'eurlex',
        act: '32024R1689',
        name: 'AI Act',
        article: 'Art. 4',
        key: 'art:4',
        version: '02024R1689-20260727',
        as_of: '2026-07-27',
        fingerprint: 'sha256:a88274d4b8172e4d063182a08c3597265711e2fe8ed0045cb415ebe14975e77f',
        state: 'current',
        changed_at: null,
        lang: 'IT',
        cited_as: ['articolo 4 del regolamento (UE) 2024/1689'],
        checked_at: '2026-11-09T05:00:00Z',
        message: null,
        current_version: null,
        current_as_of: null,
      },
      {
        source: 'eurlex',
        act: '32024R1689',
        name: 'AI Act',
        article: 'Art. 50',
        key: 'art:50',
        version: '02024R1689-20260727',
        as_of: '2026-07-27',
        fingerprint: 'sha256:17571ea8b9c51c6730c6e7242b74e446ad462369eadc7dec0b0edd52d82817a0',
        state: 'current',
        changed_at: null,
        lang: 'IT',
        cited_as: ["art. 50, par. 1, dell'AI Act"],
        checked_at: '2026-11-09T05:00:00Z',
        message: null,
        current_version: null,
        current_as_of: null,
      },
      {
        source: 'eurlex',
        act: '32024R1689',
        name: 'AI Act',
        article: 'Art. 26',
        key: 'art:26',
        version: '02024R1689-20260727',
        as_of: '2026-07-27',
        fingerprint: 'sha256:6a03d934f5f553deb958854abbc6c043f500d42339b85fe6886eced2be3bb005',
        state: 'current',
        changed_at: null,
        lang: 'IT',
        cited_as: ["art. 26, par. 2, dell'AI Act"],
        checked_at: '2026-11-09T05:00:00Z',
        message: null,
        current_version: null,
        current_as_of: null,
      },
      {
        source: 'eurlex',
        act: '32016R0679',
        name: 'GDPR',
        article: 'Art. 9',
        key: 'art:9',
        version: '02016R0679-20160504',
        as_of: '2016-05-04',
        fingerprint: 'sha256:c2e0bc20cf60e2647414d0d19a862e1bea89dfd94b3a354b99412ccb9a7ed926',
        state: 'current',
        changed_at: null,
        lang: 'IT',
        cited_as: ['art. 9 del GDPR'],
        checked_at: '2026-11-09T05:00:00Z',
        message: null,
        current_version: null,
        current_as_of: null,
      },
    ],
    rechecked_at: '2026-11-09T05:00:00Z',
  },
  {
    id: 'demo-doc-clause',
    client_id: null,
    filename: 'Processor clause (draft).txt',
    document_sha256: '1884aed51f2fe3e9c91ad2ed8b93ac417061f1e7dcda2ad639d8299d33145898',
    document_date: null,
    checked_at: '2026-10-21T13:27:00Z',
    lang: 'EN',
    watch: false,
    status: 'a_posto',
    needs_review: false,
    counts: { correggere: 0, controllare: 0, a_posto: 3, non_coperto: 0 },
    findings: [
      {
        id: 'f1',
        group: 'a_posto',
        status: { code: 'verificata', label: 'Citazione verificata' },
        line: 3,
        raw: 'Article 28(3) of Regulation (EU) 2016/679',
        context: '9.1 The Supplier acts as a processor. Under Article 28(3) of Regulation (EU) 2016/679 (GDPR), the Supplier "processes the personal data only on ...',
        act: { source: 'eurlex', id: '32016R0679', name: 'GDPR', label: 'Regulation (EU) 2016/679 (GDPR)' },
        provision: {
          key: 'art:28',
          label: 'art. 28, par. 3',
          paragraphs: ['3'],
        },
        version: { id: '02016R0679-20160504', as_of: '2016-05-04', label: 'testo consolidato al 04/05/2016' },
        url: 'https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:02016R0679-20160504',
        messages: [
          'Art. 28, par. 3 esiste nel testo consolidato al 04/05/2016.',
          'La citazione è nel testo vigente, parola per parola.',
        ],
        quotes: [
          'processes the personal data only on documented instructions from the controller',
        ],
        official_quote: 'processes the personal data only on documented instructions from the controller',
        altered_quote: null,
        differences: [],
        before: null,
        after_text: null,
        dependency: { source: 'eurlex', act: '32016R0679', key: 'art:28' },
      },
      {
        id: 'f2',
        group: 'a_posto',
        status: { code: 'valido', label: 'Riferimento valido' },
        line: 5,
        raw: 'Article 32 of the GDPR',
        context: '9.2 The Supplier applies the security measures required by Article 32 of the GDPR.',
        act: { source: 'eurlex', id: '32016R0679', name: 'GDPR', label: 'GDPR' },
        provision: { key: 'art:32', label: 'art. 32', paragraphs: [] },
        version: { id: '02016R0679-20160504', as_of: '2016-05-04', label: 'testo consolidato al 04/05/2016' },
        url: 'https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:02016R0679-20160504',
        messages: ['Art. 32 esiste nel testo consolidato al 04/05/2016.'],
        quotes: [],
        official_quote: null,
        altered_quote: null,
        differences: [],
        before: null,
        after_text: null,
        dependency: { source: 'eurlex', act: '32016R0679', key: 'art:32' },
      },
      {
        id: 'f3',
        group: 'a_posto',
        status: { code: 'verificata', label: 'Citazione verificata' },
        line: 7,
        raw: 'Article 33(2) of the GDPR',
        context: '9.3 Under Article 33(2) of the GDPR, "The processor shall notify the controller without undue delay after becoming aware of a personal data breach".',
        act: { source: 'eurlex', id: '32016R0679', name: 'GDPR', label: 'GDPR' },
        provision: {
          key: 'art:33',
          label: 'art. 33, par. 2',
          paragraphs: ['2'],
        },
        version: { id: '02016R0679-20160504', as_of: '2016-05-04', label: 'testo consolidato al 04/05/2016' },
        url: 'https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:02016R0679-20160504',
        messages: [
          'Art. 33, par. 2 esiste nel testo consolidato al 04/05/2016.',
          'La citazione è nel testo vigente, parola per parola.',
        ],
        quotes: [
          'The processor shall notify the controller without undue delay after becoming aware of a personal data breach',
        ],
        official_quote: 'The processor shall notify the controller without undue delay after becoming aware of a personal data breach',
        altered_quote: null,
        differences: [],
        before: null,
        after_text: null,
        dependency: { source: 'eurlex', act: '32016R0679', key: 'art:33' },
      },
    ],
    dependencies: [
      {
        source: 'eurlex',
        act: '32016R0679',
        name: 'GDPR',
        article: 'Art. 28',
        key: 'art:28',
        version: '02016R0679-20160504',
        as_of: '2016-05-04',
        fingerprint: 'sha256:19c9a72787910af6f890788bfff5e655e770b591675d90e62fbb29a784a5e3e5',
        state: 'current',
        changed_at: null,
        lang: 'EN',
        cited_as: ['Article 28(3) of Regulation (EU) 2016/679'],
        checked_at: '2026-10-21T13:27:00Z',
        message: null,
        current_version: null,
        current_as_of: null,
      },
      {
        source: 'eurlex',
        act: '32016R0679',
        name: 'GDPR',
        article: 'Art. 32',
        key: 'art:32',
        version: '02016R0679-20160504',
        as_of: '2016-05-04',
        fingerprint: 'sha256:cec38e071030609cd54320d0d7c54c3dbbfe81c42ca671409e5e146b97dd98ac',
        state: 'current',
        changed_at: null,
        lang: 'EN',
        cited_as: ['Article 32 of the GDPR'],
        checked_at: '2026-10-21T13:27:00Z',
        message: null,
        current_version: null,
        current_as_of: null,
      },
      {
        source: 'eurlex',
        act: '32016R0679',
        name: 'GDPR',
        article: 'Art. 33',
        key: 'art:33',
        version: '02016R0679-20160504',
        as_of: '2016-05-04',
        fingerprint: 'sha256:ff45b811f210169ec6d3562575c6f87ee1b0df2f5102e80cd0510739b49828e5',
        state: 'current',
        changed_at: null,
        lang: 'EN',
        cited_as: ['Article 33(2) of the GDPR'],
        checked_at: '2026-10-21T13:27:00Z',
        message: null,
        current_version: null,
        current_as_of: null,
      },
    ],
    rechecked_at: null,
  },
  {
    id: 'demo-doc-csddd',
    client_id: 'demo-c1',
    filename: 'Nota fornitori dovere di diligenza.docx',
    document_sha256: 'df272ff7dd7deef5377f22da4b32840780eddb035639332f37b16dfd6191467c',
    document_date: '2026-02-02',
    checked_at: '2026-02-16T10:15:00Z',
    lang: 'IT',
    watch: true,
    status: 'correggere',
    needs_review: true,
    counts: { correggere: 3, controllare: 0, a_posto: 1, non_coperto: 0 },
    findings: [
      {
        id: 'f1',
        group: 'correggere',
        status: { code: 'cambiato', label: 'Cambiato dopo il controllo' },
        line: 5,
        raw: 'articolo 2, paragrafo 1, della CSDDD',
        context: "... nella direttiva (UE) 2024/1760 (di seguito «CSDDD»). L'articolo 2, paragrafo 1, della CSDDD riguarda le società che hanno avuto «in media, più di 1 ...",
        act: { source: 'eurlex', id: '32024L1760', name: 'CSDDD', label: 'CSDDD' },
        provision: {
          key: 'art:2',
          label: 'art. 2, par. 1',
          paragraphs: ['1'],
        },
        version: { id: '02024L1760-20260318', as_of: '2026-03-18', label: 'testo consolidato al 18/03/2026' },
        url: 'https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:02024L1760-20260318',
        messages: [
          'Art. 2, par. 1 esiste nel testo consolidato al 17/04/2025.',
          'La citazione è nel testo vigente, parola per parola.',
          'Art. 2 è cambiato nel testo consolidato al 18/03/2026.',
        ],
        quotes: [
          "in media, più di 1 000 dipendenti e un fatturato netto a livello mondiale superiore a 450 000 000 EUR nell'ultimo esercizio",
        ],
        official_quote: 'in media, più di 1 000 dipendenti e un fatturato netto a livello mondiale superiore a 450 000 000 EUR nell’ultimo esercizio',
        altered_quote: null,
        differences: [],
        before: {
          version_label: 'testo consolidato al 17/04/2025',
          version_id: '02024L1760-20250417',
          as_of: '2025-04-17',
          text: 'Articolo 2\nAmbito di applicazione\n1. La presente direttiva si applica alle società che sono costituite in conformità della normativa di uno Stato membro e soddisfano una delle condizioni seguenti:\na) avere avuto, in media, più di 1 000 dipendenti e un fatturato netto a livello mondiale superiore a 450 000 000 EUR nell’ultimo esercizio per il quale è stato o avrebbe dovuto essere adottato il bilancio d’esercizio;\nb) pur senza raggiungere i limiti minimi di cui alla lettera a), essere la società capogruppo di un gruppo che ha raggiunto tali limiti minimi nell’ultimo esercizio per il quale è stato o avrebbe dovuto essere adottato il bilancio d’esercizio consolidato;\nc) aver concluso o essere la società capogruppo di un gruppo che ha concluso accordi di franchising o di licenza nell’Unione in cambio di diritti di licenza con società terze indipendenti, qualora tali accordi garantiscano un’identità comune, un concetto aziendale comune e l’applicazione di metodi aziendali uniformi, e qualora tali diritti di licenza ammontassero a più di 22 500 000 EUR nell’ultimo esercizio in cui è stato adottato o avrebbe dovuto essere adottato il bilancio annuale, e a condizione di aver registrato o di essere la società capogruppo di un gruppo che ha registrato un fatturato netto a livello mondiale superiore a 80 000 000 EUR nell’ultimo esercizio in cui è stato adottato o avrebbe dovuto essere adottato il bilancio annuale.\n2. La presente direttiva si applica alle società che sono costituite in conformità della normativa di un paese terzo e soddisfano una delle condizioni seguenti:\na) avere generato un fatturato netto superiore a 450 000 000 EUR nell’Unione nell’esercizio precedente l’ultimo esercizio;\nb) pur senza raggiungere il limite minimo di cui alla lettera a), essere la società capogruppo di un gruppo che, su base consolidata, ha raggiunto tale limite minimo nell’esercizio precedente l’ultimo esercizio;\nc) aver concluso o essere la società capogruppo di un gruppo che ha concluso accordi di franchising o di licenza nell’Unione in cambio di diritti di licenza con società terze indipendenti, qualora tali accordi garantiscano un’identità comune, un concetto aziendale comune e l’applicazione di metodi aziendali uniformi, e qualora tali diritti di licenza ammontassero a più di 22 500 000 EUR nell’Unione nell’esercizio precedente l’ultimo esercizio; e a condizione di avere generato o di essere la società capogruppo di un gruppo che ha generato un fatturato netto superiore a 80 000 000 EUR nell’Unione nell’esercizio precedente l’ultimo esercizio.\n3. Se la società capogruppo ha come attività principale la detenzione di azioni in filiazioni operative e non è coinvolta nell’adozione di decisioni gestionali, operative o finanziarie che interessano il gruppo o una o più delle sue filiazioni, può essere esentata dall’adempimento degli obblighi di cui alla presente direttiva. Tale esenzione è subordinata alla condizione che una delle filiazioni della società capogruppo stabilite nell’Unione sia designata per adempiere gli obblighi di cui agli articoli da 6 a 16 e all’articolo 22 per conto della società capogruppo, compresi gli obblighi della società capogruppo in relazione alle attività delle sue filiazioni. In tal caso alla filiazione designata sono forniti tutti i mezzi e l’autorità giuridica necessari per adempiere efficacemente tali obblighi, in particolare per garantire che la filiazione designata ottenga dalle società del gruppo le informazioni e i documenti pertinenti per adempiere gli obblighi della società capogruppo a norma della presente direttiva.\nLa società capogruppo chiede l’esenzione di cui al primo comma del presente paragrafo all’autorità di controllo competente, conformemente all’articolo 24, al fine di valutare se le condizioni di cui al primo comma del presente paragrafo sono soddisfatte. Se le condizioni sono soddisfatte, l’autorità di controllo competente concede l’esenzione. Se del caso, tale autorità informa debitamente della domanda, e successivamente della sua decisione, l’autorità di controllo competente dello Stato membro in cui è stabilita la filiazione designata.\nLa società capogruppo rimane responsabile congiuntamente con la filiazione designata per il mancato adempimento, da parte di quest’ultima, degli obblighi di cui al primo comma del presente paragrafo.\n4. Ai fini del paragrafo 1 il numero di dipendenti che lavorano a tempo parziale è calcolato su base equivalente a tempo pieno. Il personale interinale e altri lavoratori occupati in forme di lavoro atipiche sono inclusi nel calcolo del numero di dipendenti come se si trattasse di lavoratori assunti direttamente dalla società per lo stesso periodo di tempo, purché soddisfino i criteri stabiliti dalla Corte di giustizia dell’Unione europea per determinare lo status di lavoratore.\n5. La direttiva si applica alle società che soddisfano le condizioni di cui ai paragrafi 1 o 2 solo se tali condizioni sono soddisfatte per due esercizi consecutivi. La presente direttiva cessa di applicarsi alle società di cui ai paragrafi 1 o 2 qualora le condizioni stabilite in tali paragrafi non siano più soddisfatte per ciascuno degli ultimi due esercizi finanziari pertinenti.\n6. Per quanto riguarda le società di cui al paragrafo 1, lo Stato membro competente a disciplinare le materie contemplate dalla presente direttiva è lo Stato membro in cui la società ha la sede legale.\n7. Per quanto riguarda una società di cui al paragrafo 2, lo Stato membro competente a disciplinare le materie contemplate dalla presente direttiva è lo Stato membro in cui tale società ha una sede. Qualora una società non abbia una sede in nessuno Stato membro oppure abbia succursali situate in diversi Stati membri, lo Stato membro competente a disciplinare le materie contemplate dalla presente direttiva è quello in cui tale società ha generato il fatturato netto più elevato nell’Unione nell’esercizio precedente l’ultimo esercizio.\n8. La presente direttiva non si applica ai FIA, quali definiti all’articolo 4, paragrafo 1, lettera a), della direttiva 2011/61/UE del Parlamento europeo e del Consiglio (1) né agli organismi d’investimento collettivo in valori mobiliari (OICVM) ai sensi dell’articolo 1, paragrafo 2, della direttiva 2009/65/CE del Parlamento europeo e del Consiglio (2).',
        },
        after_text: 'Articolo 2\nAmbito di applicazione\n1. La presente direttiva si applica alle società che sono costituite in conformità della normativa di uno Stato membro e soddisfano una delle condizioni seguenti:\na) avere avuto, in media, più di 5 000 dipendenti e un fatturato netto a livello mondiale superiore a 1 500 000 000 EUR nell’ultimo esercizio per il quale è stato o avrebbe dovuto essere adottato il bilancio d’esercizio;\nb) pur senza raggiungere i limiti minimi di cui alla lettera a), essere la società capogruppo di un gruppo che ha raggiunto tali limiti minimi nell’ultimo esercizio per il quale è stato o avrebbe dovuto essere adottato il bilancio d’esercizio consolidato;\nc) aver concluso o essere la società capogruppo di un gruppo che ha concluso accordi di franchising o di licenza nell’Unione in cambio di diritti di licenza con società terze indipendenti, qualora tali accordi garantiscano un’identità comune, un concetto aziendale comune e l’applicazione di metodi aziendali uniformi, e qualora tali diritti di licenza ammontassero a più di 75 000 000 EUR nell’ultimo esercizio in cui è stato adottato o avrebbe dovuto essere adottato il bilancio annuale, e a condizione di aver registrato o di essere la società capogruppo di un gruppo che ha registrato un fatturato netto a livello mondiale superiore a 275 000 000 EUR nell’ultimo esercizio in cui è stato adottato o avrebbe dovuto essere adottato il bilancio annuale.\n2. La presente direttiva si applica alle società che sono costituite in conformità della normativa di un paese terzo e soddisfano una delle condizioni seguenti:\na) avere generato un fatturato netto superiore a 1 500 000 000 EUR nell’Unione nell’esercizio precedente l’ultimo esercizio;\nb) pur senza raggiungere il limite minimo di cui alla lettera a), essere la società capogruppo di un gruppo che, su base consolidata, ha raggiunto tale limite minimo nell’esercizio precedente l’ultimo esercizio;\nc) aver concluso o essere la società capogruppo di un gruppo che ha concluso accordi di franchising o di licenza nell’Unione in cambio di diritti di licenza con società terze indipendenti, qualora tali accordi garantiscano un’identità comune, un concetto aziendale comune e l’applicazione di metodi aziendali uniformi, e qualora tali diritti di licenza ammontassero a più di 75 000 000 EUR nell’Unione nell’esercizio precedente l’ultimo esercizio; e a condizione di avere generato o di essere la società capogruppo di un gruppo che ha generato un fatturato netto superiore a 275 000 000 EUR nell’Unione nell’esercizio precedente l’ultimo esercizio.\n3. Se la società capogruppo ha come attività principale la detenzione di azioni in filiazioni operative e non è coinvolta nell’adozione di decisioni gestionali, operative o finanziarie che interessano il gruppo o una o più delle sue filiazioni, può essere esentata dall’adempimento degli obblighi di cui alla presente direttiva. Tale esenzione è subordinata alla condizione che una delle filiazioni della società capogruppo stabilite nell’Unione sia designata per adempiere gli obblighi di cui agli articoli da 6 a 16 per conto della società capogruppo, compresi gli obblighi della società capogruppo in relazione alle attività delle sue filiazioni. In tal caso alla filiazione designata sono forniti tutti i mezzi e l’autorità giuridica necessari per adempiere efficacemente tali obblighi, in particolare per garantire che la filiazione designata ottenga dalle società del gruppo le informazioni e i documenti pertinenti per adempiere gli obblighi della società capogruppo a norma della presente direttiva.\nLa società capogruppo chiede l’esenzione di cui al primo comma del presente paragrafo all’autorità di controllo competente, conformemente all’articolo 24, al fine di valutare se le condizioni di cui al primo comma del presente paragrafo sono soddisfatte. Se le condizioni sono soddisfatte, l’autorità di controllo competente concede l’esenzione. Se del caso, tale autorità informa debitamente della domanda, e successivamente della sua decisione, l’autorità di controllo competente dello Stato membro in cui è stabilita la filiazione designata.\nLa società capogruppo rimane responsabile congiuntamente con la filiazione designata per il mancato adempimento, da parte di quest’ultima, degli obblighi di cui al primo comma del presente paragrafo.\n4. Ai fini del paragrafo 1 il numero di dipendenti che lavorano a tempo parziale è calcolato su base equivalente a tempo pieno. Il personale interinale e altri lavoratori occupati in forme di lavoro atipiche sono inclusi nel calcolo del numero di dipendenti come se si trattasse di lavoratori assunti direttamente dalla società per lo stesso periodo di tempo, purché soddisfino i criteri stabiliti dalla Corte di giustizia dell’Unione europea per determinare lo status di lavoratore.\n5. La direttiva si applica alle società che soddisfano le condizioni di cui ai paragrafi 1 o 2 solo se tali condizioni sono soddisfatte per due esercizi consecutivi. La presente direttiva cessa di applicarsi alle società di cui ai paragrafi 1 o 2 qualora le condizioni stabilite in tali paragrafi non siano più soddisfatte per ciascuno degli ultimi due esercizi finanziari pertinenti.\n6. Per quanto riguarda le società di cui al paragrafo 1, lo Stato membro competente a disciplinare le materie contemplate dalla presente direttiva è lo Stato membro in cui la società ha la sede legale.\n7. Per quanto riguarda una società di cui al paragrafo 2, lo Stato membro competente a disciplinare le materie contemplate dalla presente direttiva è lo Stato membro in cui tale società ha una sede. Qualora una società non abbia una sede in nessuno Stato membro oppure abbia succursali situate in diversi Stati membri, lo Stato membro competente a disciplinare le materie contemplate dalla presente direttiva è quello in cui tale società ha generato il fatturato netto più elevato nell’Unione nell’esercizio precedente l’ultimo esercizio.\n8. La presente direttiva non si applica ai FIA, quali definiti all’articolo 4, paragrafo 1, lettera a), della direttiva 2011/61/UE del Parlamento europeo e del Consiglio (1) né agli organismi d’investimento collettivo in valori mobiliari (OICVM) ai sensi dell’articolo 1, paragrafo 2, della direttiva 2009/65/CE del Parlamento europeo e del Consiglio (2).',
        dependency: { source: 'eurlex', act: '32024L1760', key: 'art:2' },
      },
      {
        id: 'f2',
        group: 'correggere',
        status: { code: 'cambiato', label: 'Cambiato dopo il controllo' },
        line: 8,
        raw: 'art. 10, par. 2, della CSDDD',
        context: "Le garanzie contrattuali che vi chiediamo sono quelle dell'art. 10, par. 2, della CSDDD.",
        act: { source: 'eurlex', id: '32024L1760', name: 'CSDDD', label: 'CSDDD' },
        provision: {
          key: 'art:10',
          label: 'art. 10, par. 2',
          paragraphs: ['2'],
        },
        version: { id: '02024L1760-20260318', as_of: '2026-03-18', label: 'testo consolidato al 18/03/2026' },
        url: 'https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:02024L1760-20260318',
        messages: [
          'Art. 10, par. 2 esiste nel testo consolidato al 17/04/2025.',
          'Art. 10 è cambiato nel testo consolidato al 18/03/2026.',
        ],
        quotes: [],
        official_quote: null,
        altered_quote: null,
        differences: [],
        before: {
          version_label: 'testo consolidato al 17/04/2025',
          version_id: '02024L1760-20250417',
          as_of: '2025-04-17',
          text: 'Articolo 10\nPrevenzione degli impatti negativi potenziali\n1. Gli Stati membri provvedono a che ciascuna società adotti misure adeguate in conformità dell’articolo 9 e del presente articolo per prevenire gli impatti negativi potenziali che sono stati o avrebbero dovuto essere individuati a norma dell’articolo 8 o, qualora la prevenzione non sia possibile o non lo sia immediatamente, per attenuarli sufficientemente.\nAl fine di stabilire le misure adeguate di cui al primo comma, si tiene debitamente conto dei seguenti elementi:\na) se l’impatto negativo potenziale può essere causato solo dalla società, se può essere causato congiuntamente dalla società e da una filiazione o da un partner commerciale, mediante atti o omissioni, o se può essere causato solo da un partner commerciale della società nella catena di attività;\nb) se l’impatto negativo potenziale può verificarsi nelle attività di una filiazione, di un partner commerciale diretto o di un partner commerciale indiretto; e\nc) la capacità della società di influenzare il partner commerciale che può causare o causare congiuntamente l’impatto negativo potenziale.\n2. La società è tenuta ad adottare le misure adeguate seguenti, ove pertinente:\na) se la natura o la complessità delle necessarie misure di prevenzione lo esige, predisporre e attuare senza indebito ritardo un piano d’azione in materia di prevenzione che preveda scadenze ragionevoli e precise per l’attuazione di misure adeguate e indicatori qualitativi e quantitativi per misurare i progressi; le società possono elaborare i loro piani d’azione in collaborazione con iniziative di settore o multipartecipative; il piano d’azione in materia di prevenzione è adattato alle attività e alle catene di attività delle società;\nb) chiedere a un partner commerciale diretto garanzie contrattuali quanto al rispetto del codice di condotta della società e, se necessario, di un piano d’azione in materia di prevenzione, anche chiedendogli di ottenere a sua volta dai partner garanzie contrattuali equivalenti per quanto le loro attività rientrino nella catena di attività della società; quando tali garanzie contrattuali sono ottenute, si applica il paragrafo 5;\nc) effettuare gli investimenti finanziari o non finanziari, gli adeguamenti o gli aggiornamenti necessari, ad esempio, degli impianti, dei processi e delle infrastrutture di produzione o di altri processi e infrastrutture operativi;\nd) apportare le modifiche o i miglioramenti necessari al piano aziendale, alle strategie generali e alle attività della società stessa, comprese le pratiche di acquisto, la progettazione e le pratiche di distribuzione;\ne) offrire sostegno mirato e proporzionato alla PMI che è partner commerciale della società, se necessario alla luce delle risorse, delle conoscenze e dei vincoli della PMI, anche fornendo o consentendo l’accesso allo sviluppo delle capacità, alla formazione o al potenziamento dei sistemi di gestione e, qualora il rispetto del codice di condotta o del piano d’azione in materia di prevenzione ne comprometta la sostenibilità economica, offrendo sostegno finanziario mirato e proporzionato, ad esempio finanziamenti diretti, prestiti a tasso agevolato, garanzie di approvvigionamento continuo o assistenza nell’ottenere finanziamenti;\nf) in conformità del diritto dell’Unione, compreso il diritto della concorrenza, collaborare con altri soggetti, se del caso anche al fine di aumentare la propria capacità di prevenire o attenuare l’impatto negativo, in particolare se nessun’altra misura risulta idonea o efficace.\n3. Le società possono adottare, se del caso, misure adeguate in aggiunta alle misure elencate nel paragrafo 2, ad esempio dialogare con un partner commerciale sulle aspettative della società per quanto riguarda la prevenzione e l’attenuazione dei potenziali impatti negativi o fornire o consentire l’accesso allo sviluppo delle capacità, a orientamenti, a un sostegno amministrativo e finanziario come prestiti o finanziamenti, tenendo conto nel contempo delle risorse, delle conoscenze e dei vincoli del partner commerciale.\n4. Per quanto riguarda gli impatti negativi potenziali che risulti impossibile prevenire o attenuare sufficientemente con le misure adeguate elencate al paragrafo 2, la società può chiedere garanzie contrattuali a un partner commerciale indiretto al fine di assicurare il rispetto del codice di condotta o del piano d’azione in materia di prevenzione. Quando tali garanzie contrattuali sono ottenute, si applica il paragrafo 5.\n5. Le garanzie contrattuali di cui al paragrafo 2, lettera b), e al paragrafo 4, sono accompagnate da misure adeguate di verifica della conformità. Ai fini della verifica della conformità, la società può richiamarsi a una verifica di terzo indipendente, anche attraverso iniziative di settore o multipartecipative.\nQuando le garanzie contrattuali sono ottenute da una PMI o il contratto è concluso con una PMI, sono previste condizioni eque, ragionevoli e non discriminatorie. La società valuta inoltre se le garanzie contrattuali di una PMI debbano essere accompagnate da alcune delle misure adeguate per le PMI di cui al paragrafo 2, lettera e). Se le misure di verifica della conformità sono attuate per una PMI, i costi della verifica di terzo indipendente sono a carico della società. La PMI può condividere i risultati delle verifiche con altre società se chiede di pagare almeno una parte dei costi della verifica di terzo indipendente, o in accordo con la società.\n6. Per quanto riguarda gli impatti negativi potenziali di cui al paragrafo 1 che risulti impossibile prevenire o attenuare sufficientemente con le misure previste dai paragrafi 2, 4 e 5, come opzione ultima la società è tenuta ad astenersi dall’allacciare un rapporto nuovo o prolungare un rapporto esistente con un partner commerciale in collegamento con il quale o nella catena di attività del quale è emerso l’impatto e, se permesso dalla legge che disciplina le relazioni con detto partner, adotta, come opzione ultima, le azioni seguenti:\na) adozione e attuazione senza indebito ritardo di un piano d’azione in materia di prevenzione rafforzato per lo specifico impatto negativo, utilizzando o aumentando l’effetto leva della società attraverso la sospensione temporanea dei rapporti d’affari in relazione alle attività in questione, purché sia ragionevole attendersi che tali iniziative vadano a buon fine; il piano d’azione comprende un calendario specifico e adeguato per l’adozione e l’attuazione di tutte le azioni ivi contenute, durante il quale la società può anche cercare partner commerciali alternativi;\nb) se non è ragionevole attendersi che tali iniziative vadano a buon fine, o se l’attuazione del piano d’azione in materia di prevenzione rafforzato non è riuscita a prevenire o attenuare l’impatto negativo, cessazione del rapporto d’affari per le attività in questione se l’impatto negativo potenziale è grave.\nPrima di sospendere temporaneamente o cessare un rapporto d’affari, la società valuta se si possa ragionevolmente prevedere che gli impatti negativi di tale sospensione o cessazione siano manifestamente più gravi dell’impatto negativo che non era possibile prevenire o attenuare sufficientemente. In tal caso, la società non è tenuta a sospendere o cessare il rapporto d’affari e deve essere in grado di riferire all’autorità di controllo competente in merito alle ragioni debitamente giustificate alla base di tale decisione.\nCiascuno Stato membro provvede a che i contratti disciplinati dal proprio diritto prevedano la possibilità di sospendere temporaneamente o cessare il rapporto d’affari in conformità del primo comma, a eccezione dei contratti che le parti sono obbligate per legge a sottoscrivere.\nQualora la società decida di sospendere temporaneamente o di cessare il rapporto d’affari, essa adotta provvedimenti volti a prevenire, attenuare o arrestare gli impatti della sospensione o della cessazione, dà un preavviso ragionevole al partner commerciale interessato e riesamina tale decisione.\nQualora decida di non sospendere temporaneamente o cessare il rapporto d’affari a norma del presente articolo, la società monitora l’impatto negativo potenziale e valuta periodicamente la sua decisione e se siano disponibili ulteriori misure adeguate.',
        },
        after_text: 'Articolo 10\nPrevenzione degli impatti negativi potenziali\n1. Gli Stati membri provvedono a che ciascuna società adotti misure adeguate in conformità dell’articolo 9 e del presente articolo per prevenire gli impatti negativi potenziali che sono stati o avrebbero dovuto essere individuati a norma dell’articolo 8 o, qualora la prevenzione non sia possibile o non lo sia immediatamente, per attenuarli sufficientemente.\nAl fine di stabilire le misure adeguate di cui al primo comma, si tiene debitamente conto dei seguenti elementi:\na) se l’impatto negativo potenziale può essere causato solo dalla società, se può essere causato congiuntamente dalla società e da una filiazione o da un partner commerciale, mediante atti o omissioni, o se può essere causato solo da un partner commerciale della società nella catena di attività;\nb) se l’impatto negativo potenziale può verificarsi nelle attività di una filiazione, di un partner commerciale diretto o di un partner commerciale indiretto; e\nc) la capacità della società di influenzare il partner commerciale che può causare o causare congiuntamente l’impatto negativo potenziale.\n2. La società è tenuta ad adottare le misure adeguate seguenti, ove pertinente:\na) se la natura o la complessità delle necessarie misure di prevenzione lo esige, predisporre e attuare senza indebito ritardo un piano d’azione in materia di prevenzione che preveda scadenze ragionevoli e precise per l’attuazione di misure adeguate e indicatori qualitativi e quantitativi per misurare i progressi; le società possono elaborare i loro piani d’azione in collaborazione con iniziative di settore o multipartecipative; il piano d’azione in materia di prevenzione è adattato alle attività e alle catene di attività delle società;\nb) chiedere a un partner commerciale diretto garanzie contrattuali quanto al rispetto del codice di condotta della società e, se necessario, di un piano d’azione in materia di prevenzione, anche chiedendogli di ottenere a sua volta dai partner garanzie contrattuali equivalenti per quanto le loro attività rientrino nella catena di attività della società; quando tali garanzie contrattuali sono ottenute, si applica il paragrafo 5;\nc) effettuare gli investimenti finanziari o non finanziari, gli adeguamenti o gli aggiornamenti necessari, ad esempio, degli impianti, dei processi e delle infrastrutture di produzione o di altri processi e infrastrutture operativi;\nd) apportare le modifiche o i miglioramenti necessari al piano aziendale, alle strategie generali e alle attività della società stessa, comprese le pratiche di acquisto, la progettazione e le pratiche di distribuzione;\ne) offrire sostegno mirato e proporzionato alla PMI che è partner commerciale della società, se necessario alla luce delle risorse, delle conoscenze e dei vincoli della PMI, anche fornendo o consentendo l’accesso allo sviluppo delle capacità, alla formazione o al potenziamento dei sistemi di gestione e, qualora il rispetto del codice di condotta o del piano d’azione in materia di prevenzione ne comprometta la sostenibilità economica, offrendo sostegno finanziario mirato e proporzionato, ad esempio finanziamenti diretti, prestiti a tasso agevolato, garanzie di approvvigionamento continuo o assistenza nell’ottenere finanziamenti;\nf) in conformità del diritto dell’Unione, compreso il diritto della concorrenza, collaborare con altri soggetti, se del caso anche al fine di aumentare la propria capacità di prevenire o attenuare l’impatto negativo, in particolare se nessun’altra misura risulta idonea o efficace.\n3. Le società possono adottare, se del caso, misure adeguate in aggiunta alle misure elencate nel paragrafo 2, ad esempio dialogare con un partner commerciale sulle aspettative della società per quanto riguarda la prevenzione e l’attenuazione dei potenziali impatti negativi o fornire o consentire l’accesso allo sviluppo delle capacità, a orientamenti, a un sostegno amministrativo e finanziario come prestiti o finanziamenti, tenendo conto nel contempo delle risorse, delle conoscenze e dei vincoli del partner commerciale.\n4. Per quanto riguarda gli impatti negativi potenziali che risulti impossibile prevenire o attenuare sufficientemente con le misure adeguate elencate al paragrafo 2, la società può chiedere garanzie contrattuali a un partner commerciale indiretto al fine di assicurare il rispetto del codice di condotta o del piano d’azione in materia di prevenzione. Quando tali garanzie contrattuali sono ottenute, si applica il paragrafo 5.\n5. Le garanzie contrattuali di cui al paragrafo 2, lettera b), e al paragrafo 4, sono accompagnate da misure adeguate di verifica della conformità. Ai fini della verifica della conformità, la società può richiamarsi a una verifica di terzo indipendente, anche attraverso iniziative di settore o multipartecipative.\nQuando le garanzie contrattuali sono ottenute da una PMI o il contratto è concluso con una PMI, sono previste condizioni eque, ragionevoli e non discriminatorie. La società valuta inoltre se le garanzie contrattuali di una PMI debbano essere accompagnate da alcune delle misure adeguate per le PMI di cui al paragrafo 2, lettera e). Se le misure di verifica della conformità sono attuate per una PMI, i costi della verifica di terzo indipendente sono a carico della società. La PMI può condividere i risultati delle verifiche con altre società se chiede di pagare almeno una parte dei costi della verifica di terzo indipendente, o in accordo con la società.\n6. Per quanto riguarda gli impatti negativi potenziali di cui al paragrafo 1 che risulti impossibile prevenire o attenuare sufficientemente con le misure previste dai paragrafi 2, 4 e 5, come opzione ultima e fino a quando l’impatto non sia stato affrontato la società:\na) si astiene dall’allacciare un rapporto nuovo o prolungare i rapporti esistenti con un partner commerciale in collegamento con il quale o nella cui catena di attività è emerso l’impatto;\nb) se permesso dalla legge che disciplina le relazioni con detto partner, sospende il rapporto d’affari per le attività in questione, anche al fine di utilizzarne o aumentarne l’effetto leva; e\nc) adotta e attua senza indebito ritardo un piano d’azione rafforzato in materia di prevenzione per lo specifico impatto negativo, purché sia ragionevole attendersi che tali iniziative vadano a buon fine.\nFinché è ragionevole attendersi che il piano rafforzato in materia di prevenzione vada a buon fine, il semplice fatto di continuare a dialogare con il partner commerciale non espone la società alle sanzioni di cui all’articolo 27 né alla responsabilità di cui all’articolo 29.\nPrima di sospendere un rapporto d’affari, la società valuta se si possa ragionevolmente prevedere che gli impatti negativi di tale sospensione siano manifestamente più gravi dell’impatto negativo che non era possibile prevenire o attenuare sufficientemente. In tal caso, la società non è tenuta a sospendere il rapporto d’affari e deve essere in grado di riferire all’autorità di controllo competente in merito alle ragioni debitamente giustificate alla base di una tale decisione.\nCiascuno Stato membro provvede a che i contratti disciplinati dal proprio diritto prevedano la possibilità di sospendere il rapporto d’affari in conformità del primo comma, a eccezione dei contratti che le parti sono obbligate per legge a sottoscrivere.\nQualora decida di sospendere il rapporto d’affari, la società adotta provvedimenti volti a prevenire, attenuare o arrestare gli impatti della sospensione, dà un preavviso ragionevole al partner commerciale interessato e riesamina tale decisione.\nQualora decida di non sospendere il rapporto d’affari a norma del presente articolo, la società monitora l’impatto negativo potenziale e valuta periodicamente la sua decisione e se siano disponibili ulteriori misure adeguate.',
        dependency: { source: 'eurlex', act: '32024L1760', key: 'art:10' },
      },
      {
        id: 'f3',
        group: 'a_posto',
        status: { code: 'valido', label: 'Riferimento valido' },
        line: 11,
        raw: 'art. 14 della CSDDD',
        context: "Il canale per le segnalazioni segue l'art. 14 della CSDDD.",
        act: { source: 'eurlex', id: '32024L1760', name: 'CSDDD', label: 'CSDDD' },
        provision: { key: 'art:14', label: 'art. 14', paragraphs: [] },
        version: { id: '02024L1760-20250417', as_of: '2025-04-17', label: 'testo consolidato al 17/04/2025' },
        url: 'https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:02024L1760-20250417',
        messages: ['Art. 14 esiste nel testo consolidato al 17/04/2025.'],
        quotes: [],
        official_quote: null,
        altered_quote: null,
        differences: [],
        before: null,
        after_text: null,
        dependency: { source: 'eurlex', act: '32024L1760', key: 'art:14' },
      },
      {
        id: 'f4',
        group: 'correggere',
        status: { code: 'cambiato', label: 'Cambiato dopo il controllo' },
        line: 14,
        raw: 'art. 37, par. 1, della CSDDD',
        context: "L'art. 37, par. 1, della CSDDD fissa il recepimento: «Gli Stati membri adottano e pubblicano, entro il 26 luglio 2027, le disposizioni legislative, ...",
        act: { source: 'eurlex', id: '32024L1760', name: 'CSDDD', label: 'CSDDD' },
        provision: {
          key: 'art:37',
          label: 'art. 37, par. 1',
          paragraphs: ['1'],
        },
        version: { id: '02024L1760-20260318', as_of: '2026-03-18', label: 'testo consolidato al 18/03/2026' },
        url: 'https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:02024L1760-20260318',
        messages: [
          'Art. 37, par. 1 esiste nel testo consolidato al 17/04/2025.',
          'La citazione è nel testo vigente, parola per parola.',
          'Art. 37 è cambiato nel testo consolidato al 18/03/2026.',
        ],
        quotes: [
          'Gli Stati membri adottano e pubblicano, entro il 26 luglio 2027, le disposizioni legislative, regolamentari e amministrative necessarie per conformarsi alla presente direttiva',
        ],
        official_quote: 'Gli Stati membri adottano e pubblicano, entro il 26 luglio 2027, le disposizioni legislative, regolamentari e amministrative necessarie per conformarsi alla presente direttiva',
        altered_quote: null,
        differences: [],
        before: {
          version_label: 'testo consolidato al 17/04/2025',
          version_id: '02024L1760-20250417',
          as_of: '2025-04-17',
          text: 'Articolo 37\nRecepimento\n1. Gli Stati membri adottano e pubblicano, entro il 26 luglio 2027, le disposizioni legislative, regolamentari e amministrative necessarie per conformarsi alla presente direttiva. Essi comunicano immediatamente alla Commissione il testo di tali disposizioni.\nEssi applicano tali disposizioni:\na) a decorrere dal 26 luglio 2028 per quanto riguarda le società di cui all’articolo 2, paragrafo 1, lettere a) e b), costituite conformemente alla legislazione dello Stato membro e che hanno avuto più di 3 000 dipendenti in media e generato un fatturato netto a livello mondiale superiore a 900 000 000 EUR nell’ultimo esercizio precedente al 26 luglio 2028 per il quale è stato adottato o avrebbe dovuto essere adottato il bilancio d’esercizio, ad eccezione delle misure necessarie per conformarsi all’articolo 16, che gli Stati membri applicano a tali società per gli esercizi aventi inizio il 1 o gennaio 2029 o successivamente a tale data;\nb) a decorrere dal 26 luglio 2028 per quanto riguarda le società di cui all’articolo 2, paragrafo 2, lettere a) e b), costituite conformemente alla legislazione di un paese terzo e che hanno generato un fatturato netto di oltre 900 000 000 EUR nell’Unione nell’esercizio antecedente all’ultimo esercizio precedente al 26 luglio 2028, ad eccezione delle misure necessarie per conformarsi all’articolo 16, che gli Stati membri applicano a tali società per gli esercizi aventi inizio il 1 o gennaio 2029 o successivamente a tale data;\nc) a decorrere dal 26 luglio 2029 per quanto riguarda tutte le altre società di cui all’articolo 2, paragrafo 1, lettere a) e b), e all’articolo 2, paragrafo 2, lettere a) e b), nonché le società di cui all’articolo 2, paragrafo 1, lettera c), e all’articolo 2, paragrafo 2, lettera c), ad eccezione delle misure necessarie per conformarsi all’articolo 16, che gli Stati membri applicano a tali società per gli esercizi finanziari aventi inizio il 1 o gennaio 2030 o successivamente a tale data.\nLe disposizioni adottate dagli Stati membri contengono un riferimento alla presente direttiva o sono corredate di tale riferimento all’atto della pubblicazione ufficiale. Le modalità del riferimento sono stabilite dagli Stati membri.\n2. Gli Stati membri comunicano alla Commissione il testo delle disposizioni fondamentali di diritto interno che adottano nel settore disciplinato dalla presente direttiva.',
        },
        after_text: 'Articolo 37\nRecepimento\n1. Gli Stati membri adottano e pubblicano, entro il 26 luglio 2028, le disposizioni legislative, regolamentari e amministrative necessarie per conformarsi alla presente direttiva. Essi comunicano immediatamente alla Commissione il testo di tali disposizioni.\nEssi applicano tali misure a decorrere dal 26 luglio 2029, ad eccezione delle misure necessarie per conformarsi all’articolo 16, che gli Stati membri applicano per gli esercizi aventi inizio il 1 o gennaio 2030 o successivamente a tale data.\nLe disposizioni adottate dagli Stati membri contengono un riferimento alla presente direttiva o sono corredate di tale riferimento all’atto della pubblicazione ufficiale. Le modalità del riferimento sono stabilite dagli Stati membri.\n2. Gli Stati membri comunicano alla Commissione il testo delle disposizioni fondamentali di diritto interno che adottano nel settore disciplinato dalla presente direttiva.',
        dependency: { source: 'eurlex', act: '32024L1760', key: 'art:37' },
      },
    ],
    dependencies: [
      {
        source: 'eurlex',
        act: '32024L1760',
        name: 'CSDDD',
        article: 'Art. 2',
        key: 'art:2',
        version: '02024L1760-20250417',
        as_of: '2025-04-17',
        fingerprint: 'sha256:05376df1d7f9867c9cec95d191559abe6d1648befe5f654f9ea2953de898ec7a',
        state: 'changed',
        changed_at: '2026-03-23T05:00:00Z',
        lang: 'IT',
        cited_as: ['articolo 2, paragrafo 1, della CSDDD'],
        checked_at: '2026-11-09T05:00:00Z',
        message: 'Art. 2 è cambiato nel testo consolidato al 18/03/2026.',
        current_version: '02024L1760-20260318',
        current_as_of: '2026-03-18',
      },
      {
        source: 'eurlex',
        act: '32024L1760',
        name: 'CSDDD',
        article: 'Art. 10',
        key: 'art:10',
        version: '02024L1760-20250417',
        as_of: '2025-04-17',
        fingerprint: 'sha256:bd5a93190b145dc14d0e1ecb94c2e884ec3d0e91bdeda7d3c247bd920d6cd9be',
        state: 'changed',
        changed_at: '2026-03-23T05:00:00Z',
        lang: 'IT',
        cited_as: ['art. 10, par. 2, della CSDDD'],
        checked_at: '2026-11-09T05:00:00Z',
        message: 'Art. 10 è cambiato nel testo consolidato al 18/03/2026.',
        current_version: '02024L1760-20260318',
        current_as_of: '2026-03-18',
      },
      {
        source: 'eurlex',
        act: '32024L1760',
        name: 'CSDDD',
        article: 'Art. 14',
        key: 'art:14',
        version: '02024L1760-20250417',
        as_of: '2025-04-17',
        fingerprint: 'sha256:ea953d8c2c9a3ca8453031d4a80e8cc28962a1e941448990e50763df3cafdba6',
        state: 'current',
        changed_at: null,
        lang: 'IT',
        cited_as: ['art. 14 della CSDDD'],
        checked_at: '2026-11-09T05:00:00Z',
        message: null,
        current_version: null,
        current_as_of: null,
      },
      {
        source: 'eurlex',
        act: '32024L1760',
        name: 'CSDDD',
        article: 'Art. 37',
        key: 'art:37',
        version: '02024L1760-20250417',
        as_of: '2025-04-17',
        fingerprint: 'sha256:167371c98a68e42e76a9555191b9e49ac4dff4d5174d93e8355ffbaab77776c6',
        state: 'changed',
        changed_at: '2026-03-23T05:00:00Z',
        lang: 'IT',
        cited_as: ['art. 37, par. 1, della CSDDD'],
        checked_at: '2026-11-09T05:00:00Z',
        message: 'Art. 37 è cambiato nel testo consolidato al 18/03/2026.',
        current_version: '02024L1760-20260318',
        current_as_of: '2026-03-18',
      },
    ],
    rechecked_at: '2026-11-09T05:00:00Z',
  },
]

/** The check the demo opens when a document is "uploaded": the file itself is never read. */
export const DEMO_UPLOAD_RESULT_ID = 'demo-doc-gdpr'

// ─── Demo answers of the documents API ──────────────────────

const BASE = '/api/v1/documents'

// What the visitor does to the examples (a deletion, the email preference)
// lives in memory only: nothing is written to the browser storage, and a
// reload of the page brings the examples back.
const deleted = new Set<string>()
let preferences: DocumentPreferences = { email_digest: true }

/** Back to the examples as shipped (used by the tests). */
export function resetDemoDocuments(): void {
  deleted.clear()
  preferences = { email_digest: true }
}

/** The demo checks still in the list, newest first. */
export function demoDocuments(): DocumentCheck[] {
  return DEMO_DOCUMENTS.filter((doc) => !deleted.has(doc.id)).sort((a, b) => b.checked_at.localeCompare(a.checked_at))
}

export function summaryOf(check: DocumentCheck): CheckSummary {
  const { findings: _findings, dependencies: _dependencies, ...summary } = check
  void _findings
  void _dependencies
  return summary
}

function notFound(): ApiError {
  // The same error the live client raises for a 404.
  return new ApiError('requestFailed', { values: { status: '404' } })
}

function find(id: string): DocumentCheck {
  const doc = demoDocuments().find((d) => d.id === id)
  if (!doc) throw notFound()
  return doc
}

function list(params: URLSearchParams): CheckList {
  const clientId = params.get('client_id')
  const needsReview = params.get('needs_review') === 'true'
  const limit = Math.max(1, Number(params.get('limit')) || 20)
  const offset = Math.max(0, Number(params.get('offset')) || 0)
  const matching = demoDocuments().filter((doc) => (!clientId || doc.client_id === clientId) && (!needsReview || doc.needs_review))
  return { items: matching.slice(offset, offset + limit).map(summaryOf), total: matching.length }
}

export type DemoRoute = { handled: false } | { handled: true; value: unknown }

const NOT_HANDLED: DemoRoute = { handled: false }
const handled = (value: unknown): DemoRoute => ({ handled: true, value })

/**
 * The demo answer for a call to the documents API, or `handled: false` for
 * any other path (the old upload route included). A check that is not in the
 * list raises the 404 the server would send.
 */
export function demoDocumentsRoute(method: string, path: string, body?: unknown): DemoRoute {
  let url: URL
  try {
    url = new URL(path, 'http://demo.invalid')
  } catch {
    return NOT_HANDLED
  }
  const route = url.pathname
  const verb = (method || 'GET').toUpperCase()

  if (route === `${BASE}/check`) {
    if (verb !== 'POST') return NOT_HANDLED
    // The example comes back to the list if it was deleted earlier.
    deleted.delete(DEMO_UPLOAD_RESULT_ID)
    return handled(find(DEMO_UPLOAD_RESULT_ID))
  }

  if (route === `${BASE}/checks`) {
    return verb === 'GET' ? handled(list(url.searchParams)) : NOT_HANDLED
  }

  if (route === `${BASE}/preferences`) {
    if (verb === 'GET') return handled({ ...preferences })
    if (verb !== 'PATCH') return NOT_HANDLED
    const wanted = (body as Partial<DocumentPreferences> | null)?.email_digest
    if (typeof wanted === 'boolean') preferences = { email_digest: wanted }
    return handled({ ...preferences })
  }

  const match = /^\/api\/v1\/documents\/checks\/([^/]+)(\/recheck|\/report)?$/.exec(route)
  if (!match) return NOT_HANDLED
  const id = decodeURIComponent(match[1])
  const action = match[2]

  if (action === '/recheck') return verb === 'POST' ? handled(find(id)) : NOT_HANDLED
  if (action === '/report') return verb === 'GET' ? handled(demoReportHtml(find(id))) : NOT_HANDLED
  if (verb === 'GET') return handled(find(id))
  if (verb === 'DELETE') {
    find(id)
    deleted.add(id)
    return handled(undefined)
  }
  return NOT_HANDLED
}

// ─── The demo report ────────────────────────────────────────
// The real report is written by the server (src/document_check/report.py).
// The demo builds a page of the same kind from the example data, in Italian
// like the server's, and says on the page that it is an example.

const GROUP_TITLES: Record<FindingGroup, string> = {
  correggere: 'Da correggere',
  controllare: 'Da controllare',
  a_posto: 'A posto',
  non_coperto: 'Non coperto',
}

const REPORT_CSS = `
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { margin: 0; background: #ffffff; color: #0c1b33; font: 16px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
main { max-width: 880px; margin: 0 auto; padding: 32px 16px 64px; }
h1 { font-size: 1.6rem; line-height: 1.25; margin: 4px 0 8px; overflow-wrap: anywhere; }
h2 { font-size: 1.15rem; margin: 40px 0 12px; }
h3 { font-size: 1rem; margin: 0; }
.kicker, .meta, footer { color: #3d4b61; }
.kicker, .meta { margin: 0; }
.summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-top: 24px; }
.tile { border: 1px solid #c3c9d3; border-radius: 8px; padding: 12px 14px; }
.tile strong { display: block; font-size: 1.6rem; line-height: 1.1; }
.card { border: 1px solid #c3c9d3; border-left-width: 6px; border-radius: 8px; padding: 14px 16px; margin: 12px 0; }
.card-head { display: flex; flex-wrap: wrap; gap: 8px 12px; align-items: baseline; }
.pill { font-size: .85rem; font-weight: 600; padding: 2px 8px; border-radius: 999px; background: #ecEEF1; }
.where { margin: 8px 0; overflow-wrap: anywhere; }
blockquote { margin: 8px 0; padding: 6px 12px; border-left: 3px solid #c3c9d3; }
.card ul { margin: 8px 0; padding-left: 20px; }
mark { background: #ffea7a; color: #0c1b33; padding: 0 2px; border-radius: 2px; }
.diff { background: #f7f8f9; border-radius: 6px; padding: 10px 12px; margin: 8px 0; overflow-wrap: anywhere; }
.diff p { margin: 4px 0; }
del { background: #f6e9ea; color: #3d4b61; text-decoration: line-through; }
ins { background: #e7f2ed; text-decoration: underline; text-decoration-thickness: 2px; }
a { color: #0a3a9c; }
footer { margin-top: 48px; font-size: .9rem; }
.correggere { border-left-color: #a3262e; } .controllare { border-left-color: #9a5b00; }
.a_posto { border-left-color: #137a4b; } .non_coperto { border-left-color: #6b7788; }
@media (max-width: 640px) { .summary { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media print { a { color: inherit; } .card { break-inside: avoid; } }
`

function escapeHtml(value: string): string {
  return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;')
}

function italianDate(iso: string | null): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso ?? '')
  return m ? `${m[3]}/${m[2]}/${m[1]}` : 'non indicata'
}

function diffHtml(before: string, after: string): string {
  return diffWords(before, after, { collapse: { longerThan: 40, keep: 15 } })
    .map((segment) => {
      if (segment.kind === 'omitted') return '[...]'
      const words = escapeHtml(segment.text)
      if (segment.kind === 'removed') return `<del>${words}</del>`
      if (segment.kind === 'added') return `<ins>${words}</ins>`
      return words
    })
    .join(' ')
}

function cardHtml(finding: Finding): string {
  const title = [finding.act?.name, finding.provision?.label ?? finding.raw].filter(Boolean).join(', ')
  const parts = [
    `<article class="card ${finding.group}"><div class="card-head">`,
    `<span class="pill">${escapeHtml(finding.status.label)}</span><h3>${escapeHtml(title)}</h3></div>`,
    `<p class="where">Riga ${finding.line}: ${escapeHtml(finding.context)}</p>`,
    ...finding.quotes.map((quote) => `<blockquote>Nel documento: «${escapeHtml(quote)}»</blockquote>`),
    `<ul>${finding.messages.map((message) => `<li>${escapeHtml(message)}</li>`).join('')}</ul>`,
  ]
  if (finding.official_quote) {
    parts.push(`<p>Testo ufficiale: <mark>${escapeHtml(finding.official_quote)}</mark></p>`)
  }
  if (finding.before && finding.after_text) {
    const now = finding.version?.label ?? 'testo vigente'
    parts.push(
      `<div class="diff"><p><strong>Differenze tra il ${escapeHtml(finding.before.version_label)} e il ${escapeHtml(now)}</strong></p>`,
      `<p>${diffHtml(finding.before.text, finding.after_text)}</p></div>`,
    )
  }
  if (finding.url) {
    const where = finding.act?.source === 'normattiva' ? 'Normattiva' : 'EUR-Lex'
    parts.push(`<p><a href="${escapeHtml(finding.url)}">Testo ufficiale su ${where}</a></p>`)
  }
  parts.push('</article>')
  return parts.join('')
}

/** The report of a demo check: one self-contained HTML page, declared as an example. */
export function demoReportHtml(check: DocumentCheck): string {
  const groups = Object.keys(GROUP_TITLES) as FindingGroup[]
  const tiles = groups
    .map((group) => `<div class="tile"><strong>${check.counts[group]}</strong><span>${GROUP_TITLES[group].toLowerCase()}</span></div>`)
    .join('')
  const sections = groups
    .map((group) => {
      const findings = check.findings.filter((f) => f.group === group)
      return findings.length ? `<section><h2>${GROUP_TITLES[group]}</h2>${findings.map(cardHtml).join('')}</section>` : ''
    })
    .join('')
  const title = escapeHtml(check.filename || 'Documento')
  return (
    '<!doctype html><html lang="it"><head><meta charset="utf-8">' +
    '<meta name="viewport" content="width=device-width, initial-scale=1">' +
    `<title>Controllo: ${title}</title><style>${REPORT_CSS}</style></head><body><main>` +
    '<header><p class="kicker">NormaAI, controllo del documento. Demo con dati di esempio.</p>' +
    `<h1>${title}</h1>` +
    `<p class="meta">Controllato il ${italianDate(check.checked_at)}. Data del documento: ${italianDate(check.document_date)}.</p></header>` +
    `<section class="summary" aria-label="Riepilogo">${tiles}</section>${sections}` +
    '<footer><p>Demo con dati di esempio: il documento, il cliente e le date sono inventati; questa pagina è costruita nel browser e non dal server. ' +
    'I testi consolidati di EUR-Lex sono documentazione: fanno fede solo i testi pubblicati nella Gazzetta ufficiale dell\'Unione europea. ' +
    'I riferimenti sono trovati in automatico e uno scritto in modo insolito può sfuggire. Non è un parere legale.</p></footer>' +
    '</main></body></html>'
  )
}
