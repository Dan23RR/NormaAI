/**
 * Canned data of the declared demo ("Demo con dati di esempio") for Controlla,
 * and the demo answers of the documents API (prefix /api/v1/documents).
 *
 * The four checks below were not written by hand: they are what the document
 * check (src/document_check) returned on 11 November 2026 for four invented
 * documents, read against the texts CELLAR serves, in the shape of the
 * documents API. So every official passage here (`official_quote`,
 * `before.text`, `after_text`) is the literal official text of the version
 * named next to it, and every outcome is one the product really gives:
 *
 * - a procedure that quotes article 33(1) GDPR with "48 ore" where the
 *   regulation says "72 ore", cites a paragraph that does not exist and puts
 *   a quote under the wrong article;
 * - an AI policy of 15 March 2026 that quotes article 4 of the AI Act as it
 *   was before Regulation (EU) 2026/1744 replaced it (consolidated text of
 *   27 July 2026), with the article then and now;
 * - an English clause checked without surveillance and without a client;
 * - a note to suppliers checked on 16 February 2026 against the CSDDD as
 *   consolidated on 17 April 2025: the re-check then found articles 2, 10 and
 *   37 changed in the consolidated text of 18 March 2026 (Directive (EU)
 *   2026/470), so the check is "da rivedere".
 *
 * The documents, the clients and the dates of the checks are invented. Only
 * the context of each reference was shortened to the 160 characters the API
 * keeps. Nothing here is a real client document.
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
        provision: { key: 'art:33', label: 'art. 33, par. 1' },
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
        differences: [{ quoted: '48', official: '72' }],
        before: null,
        after_text: null,
      },
      {
        id: 'f2',
        group: 'a_posto',
        status: { code: 'valido', label: 'Riferimento valido' },
        line: 11,
        raw: 'art. 33, par. 3, del GDPR',
        context: "La notifica contiene almeno gli elementi elencati dall'art. 33, par. 3, del GDPR.",
        act: { source: 'eurlex', id: '32016R0679', name: 'GDPR', label: 'GDPR' },
        provision: { key: 'art:33', label: 'art. 33, par. 3' },
        version: { id: '02016R0679-20160504', as_of: '2016-05-04', label: 'testo consolidato al 04/05/2016' },
        url: 'https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:02016R0679-20160504',
        messages: [
          'Art. 33, par. 3 esiste nel testo consolidato al 04/05/2016.',
        ],
        quotes: [],
        official_quote: null,
        differences: [],
        before: null,
        after_text: null,
      },
      {
        id: 'f3',
        group: 'a_posto',
        status: { code: 'verificata', label: 'Citazione verificata' },
        line: 14,
        raw: 'art. 34, par. 1, del GDPR',
        context: "L'art. 34, par. 1, del GDPR prevede che «il titolare del trattamento comunica la violazione all'interessato senza ingiustificato ritardo».",
        act: { source: 'eurlex', id: '32016R0679', name: 'GDPR', label: 'GDPR' },
        provision: { key: 'art:34', label: 'art. 34, par. 1' },
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
        differences: [],
        before: null,
        after_text: null,
      },
      {
        id: 'f4',
        group: 'controllare',
        status: { code: 'altro_articolo', label: 'Citazione in un altro articolo' },
        line: 17,
        raw: 'art. 28, par. 3, del GDPR',
        context: "In base all'art. 28, par. 3, del GDPR, il fornitore che tratta dati per conto della banca «informa il titolare del trattamento senza ingiustificato ...",
        act: { source: 'eurlex', id: '32016R0679', name: 'GDPR', label: 'GDPR' },
        provision: { key: 'art:28', label: 'art. 28, par. 3' },
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
        differences: [],
        before: null,
        after_text: null,
      },
      {
        id: 'f5',
        group: 'a_posto',
        status: { code: 'verificata', label: 'Citazione verificata' },
        line: 20,
        raw: 'art. 33, par. 5, del GDPR',
        context: "Come richiede l'art. 33, par. 5, del GDPR, «Il titolare del trattamento documenta qualsiasi violazione dei dati personali, comprese le circostanze a ...",
        act: { source: 'eurlex', id: '32016R0679', name: 'GDPR', label: 'GDPR' },
        provision: { key: 'art:33', label: 'art. 33, par. 5' },
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
        differences: [],
        before: null,
        after_text: null,
      },
      {
        id: 'f6',
        group: 'correggere',
        status: { code: 'inesistente', label: 'Non esiste nel testo vigente' },
        line: 23,
        raw: 'art. 33, par. 6, del GDPR',
        context: "Per i tempi di conservazione del registro si applica l'art. 33, par. 6, del GDPR.",
        act: { source: 'eurlex', id: '32016R0679', name: 'GDPR', label: 'GDPR' },
        provision: { key: 'art:33', label: 'art. 33, par. 6' },
        version: { id: '02016R0679-20160504', as_of: '2016-05-04', label: 'testo consolidato al 04/05/2016' },
        url: 'https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:02016R0679-20160504',
        messages: [
          "Il paragrafo 6 non esiste nel testo consolidato al 04/05/2016: l'art. 33 ha i paragrafi da 1 a 5.",
        ],
        quotes: [],
        official_quote: null,
        differences: [],
        before: null,
        after_text: null,
      },
      {
        id: 'f7',
        group: 'a_posto',
        status: { code: 'valido', label: 'Riferimento valido' },
        line: 26,
        raw: 'art. 83, par. 4, del GDPR',
        context: "La mancata notifica espone alle sanzioni dell'art. 83, par. 4, del GDPR.",
        act: { source: 'eurlex', id: '32016R0679', name: 'GDPR', label: 'GDPR' },
        provision: { key: 'art:83', label: 'art. 83, par. 4' },
        version: { id: '02016R0679-20160504', as_of: '2016-05-04', label: 'testo consolidato al 04/05/2016' },
        url: 'https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:02016R0679-20160504',
        messages: [
          'Art. 83, par. 4 esiste nel testo consolidato al 04/05/2016.',
        ],
        quotes: [],
        official_quote: null,
        differences: [],
        before: null,
        after_text: null,
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
        provision: { key: 'art:154', label: 'art. 154' },
        version: null,
        url: 'https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2003;196',
        messages: [
          'NormaAI non ha ancora i testi italiani: da controllare su Normattiva.',
        ],
        quotes: [],
        official_quote: null,
        differences: [],
        before: null,
        after_text: null,
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
      },
    ],
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
        provision: { key: 'art:4', label: 'art. 4' },
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
        differences: [],
        before: {
          version_label: 'testo originale',
          text: "Articolo 4\nAlfabetizzazione in materia di IA\nI fornitori e i deployer dei sistemi di IA adottano misure per garantire nella misura del possibile un livello sufficiente di alfabetizzazione in materia di IA del loro personale nonché di qualsiasi altra persona che si occupa del funzionamento e dell'utilizzo dei sistemi di IA per loro conto, prendendo in considerazione le loro conoscenze tecniche, la loro esperienza, istruzione e formazione, nonché il contesto in cui i sistemi di IA devono essere utilizzati, e tenendo conto delle persone o dei gruppi di persone su cui i sistemi di IA devono essere utilizzati.",
        },
        after_text: "Articolo 4\nAlfabetizzazione in materia di IA\n1. I fornitori e i deployer di sistemi di IA adottano misure volte a sostenere lo sviluppo dell'alfabetizzazione in materia di IA del loro personale nonché di qualsiasi altra persona che si occupa del funzionamento e dell'utilizzo dei sistemi di IA per loro conto, prendendo in considerazione le loro conoscenze tecniche, la loro esperienza, istruzione e formazione, nonché il contesto in cui i sistemi di IA devono essere utilizzati, e tenendo conto delle persone o dei gruppi di persone su cui i sistemi di IA devono essere utilizzati. Tale obbligo non impone ai fornitori o ai deployer di garantire un livello specifico di alfabetizzazione in materia di IA per alcuna persona.\n2. La Commissione e gli Stati membri sostengono e agevolano gli sforzi dei fornitori e dei deployer di sistemi di IA, in particolare delle PMI, nell'adempimento dell'obbligo di cui al paragrafo 1 del presente articolo. A tal fine, la Commissione pubblica esempi pratici di come adempiere a tale obbligo sulla piattaforma unica di informazione di cui all'articolo 62, paragrafo 3, lettera b).\n3. Il consiglio per l'IA adotta raccomandazioni, tenendo conto dei quadri europei delle competenze, per sostenere la Commissione e gli Stati membri nella promozione dell'alfabetizzazione in materia di IA richiesta a norma del paragrafo 1, anche stabilendo obiettivi comuni.",
      },
      {
        id: 'f2',
        group: 'a_posto',
        status: { code: 'verificata', label: 'Citazione verificata' },
        line: 8,
        raw: "art. 50, par. 1, dell'AI Act",
        context: "Gli assistenti virtuali rispettano l'art. 50, par. 1, dell'AI Act: le persone devono essere «informate del fatto di stare interagendo con un sistema di IA».",
        act: { source: 'eurlex', id: '32024R1689', name: 'AI Act', label: 'AI Act' },
        provision: { key: 'art:50', label: 'art. 50, par. 1' },
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
        differences: [],
        before: null,
        after_text: null,
      },
      {
        id: 'f3',
        group: 'a_posto',
        status: { code: 'verificata', label: 'Citazione verificata' },
        line: 11,
        raw: "art. 26, par. 2, dell'AI Act",
        context: "... i sistemi ad alto rischio si applica l'art. 26, par. 2, dell'AI Act: «I deployer affidano la sorveglianza umana a persone fisiche che dispongono della ...",
        act: { source: 'eurlex', id: '32024R1689', name: 'AI Act', label: 'AI Act' },
        provision: { key: 'art:26', label: 'art. 26, par. 2' },
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
        differences: [],
        before: null,
        after_text: null,
      },
      {
        id: 'f4',
        group: 'a_posto',
        status: { code: 'valido', label: 'Riferimento valido' },
        line: 14,
        raw: 'art. 9 del GDPR',
        context: "Il trattamento dei dati relativi alla salute segue l'art. 9 del GDPR.",
        act: { source: 'eurlex', id: '32016R0679', name: 'GDPR', label: 'GDPR' },
        provision: { key: 'art:9', label: 'art. 9' },
        version: { id: '02016R0679-20160504', as_of: '2016-05-04', label: 'testo consolidato al 04/05/2016' },
        url: 'https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:02016R0679-20160504',
        messages: [
          'Art. 9 esiste nel testo consolidato al 04/05/2016.',
        ],
        quotes: [],
        official_quote: null,
        differences: [],
        before: null,
        after_text: null,
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
      },
    ],
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
        context: '... Supplier acts as a processor. Under Article 28(3) of Regulation (EU) 2016/679 (GDPR), the Supplier "processes the personal data only on documented ...',
        act: { source: 'eurlex', id: '32016R0679', name: 'GDPR', label: 'Regulation (EU) 2016/679 (GDPR)' },
        provision: { key: 'art:28', label: 'art. 28, par. 3' },
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
        differences: [],
        before: null,
        after_text: null,
      },
      {
        id: 'f2',
        group: 'a_posto',
        status: { code: 'valido', label: 'Riferimento valido' },
        line: 5,
        raw: 'Article 32 of the GDPR',
        context: '9.2 The Supplier applies the security measures required by Article 32 of the GDPR.',
        act: { source: 'eurlex', id: '32016R0679', name: 'GDPR', label: 'GDPR' },
        provision: { key: 'art:32', label: 'art. 32' },
        version: { id: '02016R0679-20160504', as_of: '2016-05-04', label: 'testo consolidato al 04/05/2016' },
        url: 'https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:02016R0679-20160504',
        messages: [
          'Art. 32 esiste nel testo consolidato al 04/05/2016.',
        ],
        quotes: [],
        official_quote: null,
        differences: [],
        before: null,
        after_text: null,
      },
      {
        id: 'f3',
        group: 'a_posto',
        status: { code: 'verificata', label: 'Citazione verificata' },
        line: 7,
        raw: 'Article 33(2) of the GDPR',
        context: '9.3 Under Article 33(2) of the GDPR, "The processor shall notify the controller without undue delay after becoming aware of a personal data breach".',
        act: { source: 'eurlex', id: '32016R0679', name: 'GDPR', label: 'GDPR' },
        provision: { key: 'art:33', label: 'art. 33, par. 2' },
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
        differences: [],
        before: null,
        after_text: null,
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
      },
    ],
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
    status: 'a_posto',
    needs_review: true,
    counts: { correggere: 0, controllare: 0, a_posto: 4, non_coperto: 0 },
    findings: [
      {
        id: 'f1',
        group: 'a_posto',
        status: { code: 'verificata', label: 'Citazione verificata' },
        line: 5,
        raw: 'articolo 2, paragrafo 1, della CSDDD',
        context: "... 2024/1760 (di seguito «CSDDD»). L'articolo 2, paragrafo 1, della CSDDD riguarda le società che hanno avuto «in media, più di 1 000 dipendenti e un ...",
        act: { source: 'eurlex', id: '32024L1760', name: 'CSDDD', label: 'CSDDD' },
        provision: { key: 'art:2', label: 'art. 2, par. 1' },
        version: { id: '02024L1760-20250417', as_of: '2025-04-17', label: 'testo consolidato al 17/04/2025' },
        url: 'https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:02024L1760-20250417',
        messages: [
          'Art. 2, par. 1 esiste nel testo consolidato al 17/04/2025.',
          'La citazione è nel testo vigente, parola per parola.',
        ],
        quotes: [
          "in media, più di 1 000 dipendenti e un fatturato netto a livello mondiale superiore a 450 000 000 EUR nell'ultimo esercizio",
        ],
        official_quote: 'in media, più di 1 000 dipendenti e un fatturato netto a livello mondiale superiore a 450 000 000 EUR nell’ultimo esercizio',
        differences: [],
        before: null,
        after_text: null,
      },
      {
        id: 'f2',
        group: 'a_posto',
        status: { code: 'valido', label: 'Riferimento valido' },
        line: 8,
        raw: 'art. 10, par. 2, della CSDDD',
        context: "Le garanzie contrattuali che vi chiediamo sono quelle dell'art. 10, par. 2, della CSDDD.",
        act: { source: 'eurlex', id: '32024L1760', name: 'CSDDD', label: 'CSDDD' },
        provision: { key: 'art:10', label: 'art. 10, par. 2' },
        version: { id: '02024L1760-20250417', as_of: '2025-04-17', label: 'testo consolidato al 17/04/2025' },
        url: 'https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:02024L1760-20250417',
        messages: [
          'Art. 10, par. 2 esiste nel testo consolidato al 17/04/2025.',
        ],
        quotes: [],
        official_quote: null,
        differences: [],
        before: null,
        after_text: null,
      },
      {
        id: 'f3',
        group: 'a_posto',
        status: { code: 'valido', label: 'Riferimento valido' },
        line: 11,
        raw: 'art. 14 della CSDDD',
        context: "Il canale per le segnalazioni segue l'art. 14 della CSDDD.",
        act: { source: 'eurlex', id: '32024L1760', name: 'CSDDD', label: 'CSDDD' },
        provision: { key: 'art:14', label: 'art. 14' },
        version: { id: '02024L1760-20250417', as_of: '2025-04-17', label: 'testo consolidato al 17/04/2025' },
        url: 'https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:02024L1760-20250417',
        messages: [
          'Art. 14 esiste nel testo consolidato al 17/04/2025.',
        ],
        quotes: [],
        official_quote: null,
        differences: [],
        before: null,
        after_text: null,
      },
      {
        id: 'f4',
        group: 'a_posto',
        status: { code: 'verificata', label: 'Citazione verificata' },
        line: 14,
        raw: 'art. 37, par. 1, della CSDDD',
        context: "L'art. 37, par. 1, della CSDDD fissa il recepimento: «Gli Stati membri adottano e pubblicano, entro il 26 luglio 2027, le disposizioni legislative, ...",
        act: { source: 'eurlex', id: '32024L1760', name: 'CSDDD', label: 'CSDDD' },
        provision: { key: 'art:37', label: 'art. 37, par. 1' },
        version: { id: '02024L1760-20250417', as_of: '2025-04-17', label: 'testo consolidato al 17/04/2025' },
        url: 'https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:02024L1760-20250417',
        messages: [
          'Art. 37, par. 1 esiste nel testo consolidato al 17/04/2025.',
          'La citazione è nel testo vigente, parola per parola.',
        ],
        quotes: [
          'Gli Stati membri adottano e pubblicano, entro il 26 luglio 2027, le disposizioni legislative, regolamentari e amministrative necessarie per conformarsi alla presente direttiva',
        ],
        official_quote: 'Gli Stati membri adottano e pubblicano, entro il 26 luglio 2027, le disposizioni legislative, regolamentari e amministrative necessarie per conformarsi alla presente direttiva',
        differences: [],
        before: null,
        after_text: null,
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
      },
    ],
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
