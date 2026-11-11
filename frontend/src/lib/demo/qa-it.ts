/**
 * Demo answers of "Chiedi", Italian. They mirror what the backend returns from
 * POST /api/v1/qa. Every passage marked `verified: true` is the official
 * Italian text, word for word, in the version named in acts.ts: run
 * `python scripts/check_demo_quotes.py` after any edit. Citations of texts
 * that are not in the corpus (Italian law, the delegated acts of July 2026)
 * are left unverified on purpose, so the demo shows that state too.
 *
 * Facts checked on EUR-Lex and Normattiva on 2026-11-11. The same scenarios,
 * with the same citations in the same order, live in qa-en.ts.
 */
import type { DemoCitation, DemoQAResponse, DemoQAScenario } from './types'

const AI_ACT_ART50_QUOTE =
  'I fornitori garantiscono che i sistemi di IA destinati a interagire direttamente con le persone fisiche sono progettati e sviluppati in modo tale che le persone fisiche interessate siano informate del fatto di stare interagendo con un sistema di IA'

const AI_ACT_ART9_QUOTE =
  'In relazione ai sistemi di IA ad alto rischio è istituito, attuato, documentato e mantenuto un sistema di gestione dei rischi.'

const AI_ACT_ART113_QUOTE =
  'Si applica a decorrere dal 2 agosto 2026.'

const AI_ACT_ART113_ANNEX3_QUOTE =
  "2 dicembre 2027 per quanto riguarda i sistemi di IA classificati come ad alto rischio ai sensi dell'articolo 6, paragrafo 2, e dell'allegato III"

const AI_ACT_ART99_SME_QUOTE =
  "Nel caso delle PMI, comprese le start-up, ciascuna sanzione pecuniaria di cui al presente articolo è pari al massimo alle percentuali o all'importo di cui ai paragrafi 3, 4 e 5, se inferiore."

const ACCOUNTING_ART19A_SCOPE_QUOTE =
  "Le imprese che, alla data di chiusura del bilancio, presentano ricavi netti delle vendite e delle prestazioni superiori a 450 000 000 EUR e superano un numero medio di 1 000 dipendenti occupati durante l'esercizio includono nella relazione sulla gestione informazioni necessarie alla comprensione dell'impatto dell'impresa sulle questioni di sostenibilità"

const ACCOUNTING_ART19A_PROTECTED_QUOTE =
  'Le imprese protette hanno il diritto di rifiutarsi di fornire informazioni in più rispetto a quelle specificate nei principi volontari'

const CSDDD_ART5_QUOTE =
  'Gli Stati membri provvedono a che ciascuna società eserciti il dovere di diligenza basato sul rischio in materia di diritti umani e di ambiente di cui agli articoli da 7 a 16 («dovere di diligenza»)'

const CSDDD_ART8_PARTNERS_QUOTE =
  'le società possano chiedere informazioni ai partner commerciali soltanto qualora tali informazioni siano necessarie, e nel caso di partner commerciali con meno di 5 000 dipendenti soltanto qualora le informazioni non possano ragionevolmente essere ottenute con altri mezzi'

const DORA_ART6_QUOTE =
  "Nell'ambito del sistema di gestione globale del rischio, le entità finanziarie predispongono un quadro per la gestione dei rischi informatici solido, esaustivo e adeguatamente documentato"

const DORA_ART19_QUOTE =
  "Le entità finanziarie segnalano gli gravi incidenti TIC all'autorità competente interessata di cui all'articolo 46"

const DORA_ART28_QUOTE =
  'Le entità finanziarie gestiscono i rischi informatici derivanti da terzi quali componenti integranti dei rischi informatici nel contesto del proprio quadro per la gestione di detti rischi'

const NIS2_ART23_4A_QUOTE =
  "senza indebito ritardo, e comunque entro 24 ore da quando sono venuti a conoscenza dell'incidente significativo, un preallarme"

const GDPR_ART37_QUOTE =
  'Il titolare del trattamento e il responsabile del trattamento designano sistematicamente un responsabile della protezione dei dati ogniqualvolta'

/** The voluntary standard of July 2026 is not one of the acts of the corpus: cited, not verified. */
const VOLUNTARY_STANDARD: DemoCitation = {
  framework: 'CSRD',
  title: 'Regolamento delegato (UE) 2026/1560',
  reference: 'art. 3 e allegato II (limite per la catena del valore)',
  quote_snippet: '',
  celex: '32026R1560',
  verified: false,
}

const VOLUNTARY_STANDARD_CAVEAT =
  'Il Regolamento delegato (UE) 2026/1560 sui principi volontari non è tra gli atti del corpus: la citazione che lo riguarda resta da verificare su EUR-Lex.'

const ITALIAN_LAW_CAVEAT =
  'La normativa italiana non è ancora nel corpus di Chiedi: la citazione che la riguarda resta da verificare su Normattiva.'

export const QA_IT: Record<DemoQAScenario, DemoQAResponse> = {
  csrd: {
    answer:
      "Dopo l'Omnibus I (Direttiva (UE) 2026/470, in vigore dal 18 marzo 2026) la rendicontazione di sostenibilità è obbligatoria solo per le imprese che superano entrambe le soglie: ricavi netti oltre 450 milioni di euro e più di 1.000 dipendenti in media nell'esercizio [1]. Le condizioni sono cumulative: un'impresa con 600 dipendenti resta fuori dall'obbligo, qualunque sia il fatturato. Il nuovo perimetro si applica agli esercizi che iniziano dal 1° gennaio 2027 [2]; per gli esercizi 2025 e 2026 gli Stati membri possono esentare le imprese della prima ondata che non superano le nuove soglie [3].\n\nChi resta sotto le soglie può comunque ricevere richieste di dati da un cliente obbligato. La direttiva protegge le imprese fino a 1.000 dipendenti che stanno nella catena del valore di un'impresa obbligata: hanno il diritto di rifiutare le informazioni che vanno oltre i principi volontari [4], fissati dal Regolamento delegato (UE) 2026/1560 [5].\n\nIn Italia la CSRD è recepita dal D.Lgs. 125/2024. Il D.L. 23 ottobre 2026, n. 193 ha escluso dal decreto, per gli esercizi che iniziano nel 2026 e nel 2027, le imprese con ricavi netti non superiori a 450 milioni di euro o con non più di 1.000 dipendenti [6]. Le modifiche della direttiva vanno recepite entro il 19 marzo 2027 [7].",
    citations: [
      {
        framework: 'CSRD',
        reference: 'art. 19 bis, par. 1, della Direttiva 2013/34/UE',
        quote_snippet: ACCOUNTING_ART19A_SCOPE_QUOTE,
        celex: '32013L0034',
        verified: true,
      },
      {
        framework: 'CSRD',
        reference: 'art. 5, par. 2, primo comma, lett. b)',
        quote_snippet: 'per gli esercizi aventi inizio il 1° gennaio 2027 o in data successiva',
        celex: '32022L2464',
        verified: true,
      },
      {
        framework: 'CSRD',
        reference: 'art. 5, par. 2, ultimo comma',
        quote_snippet:
          "gli Stati membri possono esentare, se del caso, le imprese o gli emittenti che, su base consolidata, non presentano ricavi netti delle vendite e delle prestazioni superiori a 450 000 000 EUR o non superano un numero medio di 1 000 dipendenti occupati durante l'esercizio",
        celex: '32022L2464',
        verified: true,
      },
      {
        framework: 'CSRD',
        reference: 'art. 19 bis, par. 3, della Direttiva 2013/34/UE',
        quote_snippet: ACCOUNTING_ART19A_PROTECTED_QUOTE,
        celex: '32013L0034',
        verified: true,
      },
      VOLUNTARY_STANDARD,
      {
        framework: 'IT',
        title: 'D.L. 23 ottobre 2026, n. 193',
        reference: "art. 10 (nuovo comma 3-bis dell'art. 17 del D.Lgs. 125/2024)",
        quote_snippet: '',
        url: 'https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legge:2026-10-23;193',
        verified: false,
      },
      {
        framework: 'CSRD',
        title: 'Direttiva (UE) 2026/470 (Omnibus I)',
        reference: 'art. 5, par. 1',
        quote_snippet:
          'Gli Stati membri mettono in vigore le disposizioni legislative, regolamentari e amministrative necessarie per conformarsi agli articoli 1, 2 e 3 entro il 19 marzo 2027.',
        celex: '32026L0470',
        verified: true,
      },
    ],
    confidence_score: 0.86,
    requires_expert_review: true,
    related_frameworks: ['CSDDD', 'TAXONOMY'],
    caveats: [
      VOLUNTARY_STANDARD_CAVEAT,
      ITALIAN_LAW_CAVEAT,
      'Il D.L. 193/2026 è un decreto-legge: va convertito in legge entro sessanta giorni dalla pubblicazione e il testo può cambiare.',
    ],
  },
  csddd: {
    answer:
      "La CSDDD (Direttiva (UE) 2024/1760) impone alle imprese più grandi un dovere di diligenza sui diritti umani e sull'ambiente lungo la catena di attività: integrarlo nelle politiche aziendali, individuare e valutare gli impatti negativi, prevenirli o farli cessare, renderne conto [1]. Dopo l'Omnibus I (Direttiva (UE) 2026/470) riguarda le società con più di 5.000 dipendenti in media e un fatturato netto mondiale superiore a 1,5 miliardi di euro [2]: una PMI non ha obblighi diretti.\n\nIl calendario è stato riscritto: gli Stati membri recepiscono entro il 26 luglio 2028 [3] e le regole si applicano dal 26 luglio 2029 [4]. Lo stesso atto ha soppresso l'articolo 22 sul piano di transizione climatica e il primo paragrafo dell'articolo 29, che armonizzava la responsabilità civile.\n\nPer un fornitore conta soprattutto un limite nuovo: le società obbligate possono chiedere informazioni ai partner commerciali solo se necessarie e, quando il partner ha meno di 5.000 dipendenti, solo se non possono ragionevolmente ottenerle in altro modo [5]. Le società in ambito devono inoltre ricevere i reclami di chi teme un impatto negativo [6].",
    citations: [
      {
        framework: 'CSDDD',
        reference: 'art. 5, par. 1',
        quote_snippet: CSDDD_ART5_QUOTE,
        celex: '32024L1760',
        verified: true,
      },
      {
        framework: 'CSDDD',
        reference: 'art. 2, par. 1, lett. a)',
        quote_snippet:
          "avere avuto, in media, più di 5 000 dipendenti e un fatturato netto a livello mondiale superiore a 1 500 000 000 EUR nell'ultimo esercizio per il quale è stato o avrebbe dovuto essere adottato il bilancio d'esercizio",
        celex: '32024L1760',
        verified: true,
      },
      {
        framework: 'CSDDD',
        reference: 'art. 37, par. 1, primo comma',
        quote_snippet:
          'Gli Stati membri adottano e pubblicano, entro il 26 luglio 2028, le disposizioni legislative, regolamentari e amministrative necessarie per conformarsi alla presente direttiva.',
        celex: '32024L1760',
        verified: true,
      },
      {
        framework: 'CSDDD',
        reference: 'art. 37, par. 1, secondo comma',
        quote_snippet: 'Essi applicano tali misure a decorrere dal 26 luglio 2029',
        celex: '32024L1760',
        verified: true,
      },
      {
        framework: 'CSDDD',
        reference: 'art. 8, par. 2 bis, lett. a)',
        quote_snippet: CSDDD_ART8_PARTNERS_QUOTE,
        celex: '32024L1760',
        verified: true,
      },
      {
        framework: 'CSDDD',
        reference: 'art. 14, par. 1',
        quote_snippet:
          'consenta alle persone e ai soggetti elencati al paragrafo 2 di presentarle un reclamo qualora tali persone o soggetti nutrano un legittimo timore circa gli impatti negativi, siano essi effettivi o potenziali',
        celex: '32024L1760',
        verified: true,
      },
    ],
    confidence_score: 0.9,
    requires_expert_review: false,
    related_frameworks: ['CSRD'],
    caveats: ['Le regole nazionali di recepimento, attese entro il 26 luglio 2028, possono precisare obblighi e sanzioni.'],
  },
  value_chain: {
    answer:
      "Dipende dal motivo della richiesta. Se il cliente raccoglie dati per la propria rendicontazione di sostenibilità e la tua impresa non supera i 1.000 dipendenti, sei un'«impresa protetta» [1]: hai il diritto di rifiutare le informazioni che vanno oltre i principi volontari [2] e una clausola contrattuale che le imponga non è vincolante [3]. Il cliente deve anche dirti quali richieste superano quel limite e che puoi rifiutarle. I principi volontari e l'elenco delle informazioni coperte dal limite sono nel Regolamento delegato (UE) 2026/1560 [4]; il limite si applica dagli esercizi che iniziano dal 1° gennaio 2027.\n\nSe invece il cliente è una società soggetta alla CSDDD e ti interpella per il proprio dovere di diligenza, vale un'altra regola: può chiedere informazioni solo se necessarie e, a un partner con meno di 5.000 dipendenti, solo se non può ragionevolmente ottenerle in altro modo [5].\n\nIl limite della rendicontazione non copre le richieste fatte per altri scopi, per esempio quelle di una banca per concedere credito: il regolamento si limita a incoraggiare banche e assicurazioni a restare nel perimetro dei principi volontari.",
    citations: [
      {
        framework: 'CSRD',
        reference: 'art. 19 bis, par. 3, della Direttiva 2013/34/UE (definizione di impresa protetta)',
        quote_snippet:
          "alla data di chiusura del bilancio, non supera un numero medio di 1 000 dipendenti occupati durante l'esercizio precedente",
        celex: '32013L0034',
        verified: true,
      },
      {
        framework: 'CSRD',
        reference: 'art. 19 bis, par. 3, della Direttiva 2013/34/UE',
        quote_snippet: ACCOUNTING_ART19A_PROTECTED_QUOTE,
        celex: '32013L0034',
        verified: true,
      },
      {
        framework: 'CSRD',
        reference: 'art. 19 bis, par. 3, quarto comma, lett. b), della Direttiva 2013/34/UE',
        quote_snippet: 'qualsiasi disposizione contrattuale contraria alla lettera a) non è vincolante',
        celex: '32013L0034',
        verified: true,
      },
      VOLUNTARY_STANDARD,
      {
        framework: 'CSDDD',
        reference: 'art. 8, par. 2 bis, lett. a)',
        quote_snippet: CSDDD_ART8_PARTNERS_QUOTE,
        celex: '32024L1760',
        verified: true,
      },
    ],
    confidence_score: 0.87,
    requires_expert_review: false,
    related_frameworks: ['CSRD', 'CSDDD'],
    caveats: [VOLUNTARY_STANDARD_CAVEAT],
  },
  ai_act: {
    answer:
      "Il Regolamento (UE) 2024/1689 (AI Act) gradua gli obblighi in base al rischio. Alcune pratiche sono vietate, per esempio i sistemi che usano tecniche subliminali o manipolative per distorcere il comportamento delle persone [1]. Sono ad alto rischio i sistemi elencati nell'allegato III [2], tra cui quelli usati per selezionare il personale [3] o per valutare il merito di credito, e quelli che sono componenti di sicurezza di prodotti regolamentati: per questi è istituito un sistema di gestione dei rischi [4], con governance dei dati, documentazione tecnica, trasparenza e sorveglianza umana.\n\nIl regolamento si applica dal 2 agosto 2026 [5], ma il Regolamento (UE) 2026/1744 ha spostato le date dell'alto rischio: 2 dicembre 2027 per i sistemi dell'allegato III [6] e 2 agosto 2028 per quelli legati ai prodotti dell'allegato I [7]. Gli obblighi di trasparenza dell'articolo 50 (assistenti virtuali, contenuti sintetici) valgono già dal 2 agosto 2026.\n\nLe sanzioni per le pratiche vietate arrivano a 35 milioni di euro o al 7% del fatturato mondiale annuo, se superiore [8]; per le PMI vale il minore dei due importi [9].",
    citations: [
      {
        framework: 'AI_ACT',
        reference: 'art. 5, par. 1, lett. a)',
        quote_snippet:
          "l'immissione sul mercato, la messa in servizio o l'uso di un sistema di IA che utilizza tecniche subliminali che agiscono senza che una persona ne sia consapevole o tecniche volutamente manipolative o ingannevoli",
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'art. 6, par. 2',
        quote_snippet:
          "Oltre ai sistemi di IA ad alto rischio di cui al paragrafo 1, sono considerati ad alto rischio anche i sistemi di IA di cui all'allegato III.",
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'allegato III, punto 4, lett. a)',
        quote_snippet:
          "i sistemi di IA destinati a essere utilizzati per l'assunzione o la selezione di persone fisiche, in particolare per pubblicare annunci di lavoro mirati, analizzare o filtrare le candidature e valutare i candidati",
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'art. 9, par. 1',
        quote_snippet: AI_ACT_ART9_QUOTE,
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'art. 113, secondo comma',
        quote_snippet: AI_ACT_ART113_QUOTE,
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'art. 113, terzo comma, lett. c), punto i)',
        quote_snippet: AI_ACT_ART113_ANNEX3_QUOTE,
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'art. 113, terzo comma, lett. c), punto ii)',
        quote_snippet:
          "2 agosto 2028 per quanto riguarda i sistemi di IA classificati come ad alto rischio ai sensi dell'articolo 6, paragrafo 1, e dell'allegato I",
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'art. 99, par. 3',
        quote_snippet:
          "La non conformità al divieto delle pratiche di IA di cui all'articolo 5 è soggetta a sanzioni amministrative pecuniarie fino a 35 000 000 EUR o, se l'autore del reato è un'impresa, fino al 7 % del fatturato mondiale totale annuo dell'esercizio precedente, se superiore.",
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'art. 99, par. 6',
        quote_snippet: AI_ACT_ART99_SME_QUOTE,
        celex: '32024R1689',
        verified: true,
      },
    ],
    confidence_score: 0.93,
    requires_expert_review: false,
    related_frameworks: ['GDPR'],
    caveats: [
      "La classificazione di un sistema come ad alto rischio dipende dall'uso concreto: l'articolo 6, paragrafo 3, esclude i sistemi dell'allegato III che non presentano un rischio significativo.",
    ],
  },
  ai_act_art50: {
    answer:
      "Sì. L'articolo 50, paragrafo 1, del Regolamento (UE) 2024/1689 obbliga chi fornisce un sistema di IA destinato a interagire direttamente con le persone a progettarlo in modo che le persone sappiano di parlare con un'IA, salvo che sia evidente per una persona ragionevolmente informata, attenta e avveduta [1]. L'informazione va data in modo chiaro e distinguibile al più tardi alla prima interazione [2]: per un assistente sul sito aziendale basta una dichiarazione esplicita all'avvio della conversazione. L'obbligo di progettazione è del fornitore del sistema; all'impresa che lo adotta sul proprio sito conviene controllare che l'avviso ci sia.\n\nL'obbligo si applica dal 2 agosto 2026 [3]. Se l'assistente genera testi, audio o immagini, il fornitore deve anche marcare gli output come generati artificialmente [4]; per i sistemi già sul mercato prima del 2 agosto 2026 il termine per adeguarsi è il 2 dicembre 2026 [5].\n\nLa violazione degli obblighi di trasparenza è punita con sanzioni fino a 15 milioni di euro o al 3% del fatturato mondiale annuo, se superiore [6]; per le PMI e le start-up vale il minore dei due importi [7].",
    citations: [
      {
        framework: 'AI_ACT',
        reference: 'art. 50, par. 1',
        quote_snippet: AI_ACT_ART50_QUOTE,
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'art. 50, par. 5',
        quote_snippet:
          'Le informazioni di cui ai paragrafi da 1 a 4 sono fornite alle persone fisiche interessate in maniera chiara e distinguibile al più tardi al momento della prima interazione o esposizione.',
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'art. 113, secondo comma',
        quote_snippet: AI_ACT_ART113_QUOTE,
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'art. 50, par. 2',
        quote_snippet:
          'garantiscono che gli output del sistema di IA siano marcati in un formato leggibile meccanicamente e rilevabili come generati o manipolati artificialmente',
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'art. 111, par. 4',
        quote_snippet:
          "immessi sul mercato prima del 2 agosto 2026, adottano le misure necessarie per conformarsi all'articolo 50, paragrafo 2, entro il 2 dicembre 2026",
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'art. 99, par. 4',
        quote_snippet:
          "è soggetta a sanzioni amministrative pecuniarie fino a 15 000 000 EUR o, se l'autore del reato è un'impresa, fino al 3 % del fatturato mondiale totale annuo dell'esercizio precedente, se superiore",
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'art. 99, par. 6',
        quote_snippet: AI_ACT_ART99_SME_QUOTE,
        celex: '32024R1689',
        verified: true,
      },
    ],
    confidence_score: 0.94,
    requires_expert_review: false,
    related_frameworks: ['GDPR'],
    caveats: [],
  },
  ai_act_art4: {
    answer:
      "L'articolo 4 dell'AI Act, nel testo sostituito dal Regolamento (UE) 2026/1744, chiede a fornitori e deployer (chi usa un sistema di IA nella propria attività) di adottare misure che sostengano l'alfabetizzazione in materia di IA del personale e di chi usa i sistemi per loro conto, tenendo conto di conoscenze, esperienza e contesto d'uso [1]. Non c'è un livello da raggiungere né un attestato da ottenere: l'obbligo non impone di garantire un livello specifico di alfabetizzazione per alcuna persona [2].\n\nIn pratica conviene sapere quali sistemi di IA sono in uso, dare a chi li usa istruzioni proporzionate (cosa fanno, quali limiti hanno, quando serve un controllo umano) e conservare traccia di quanto fatto. Commissione e Stati membri devono sostenere le imprese, in particolare le PMI [3], e la Commissione pubblica esempi pratici di come adempiere.",
    citations: [
      {
        framework: 'AI_ACT',
        reference: 'art. 4, par. 1',
        quote_snippet:
          "I fornitori e i deployer di sistemi di IA adottano misure volte a sostenere lo sviluppo dell'alfabetizzazione in materia di IA del loro personale nonché di qualsiasi altra persona che si occupa del funzionamento e dell'utilizzo dei sistemi di IA per loro conto",
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'art. 4, par. 1, ultima frase',
        quote_snippet:
          'Tale obbligo non impone ai fornitori o ai deployer di garantire un livello specifico di alfabetizzazione in materia di IA per alcuna persona.',
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'art. 4, par. 2',
        quote_snippet:
          "La Commissione e gli Stati membri sostengono e agevolano gli sforzi dei fornitori e dei deployer di sistemi di IA, in particolare delle PMI, nell'adempimento dell'obbligo di cui al paragrafo 1 del presente articolo.",
        celex: '32024R1689',
        verified: true,
      },
    ],
    confidence_score: 0.93,
    requires_expert_review: false,
    related_frameworks: ['GDPR'],
    caveats: ["Il testo dell'articolo 4 è quello in vigore dal 27 luglio 2026: le guide scritte prima di quella data descrivono un obbligo diverso."],
  },
  ai_act_art9: {
    answer:
      "L'articolo 9 dell'AI Act impone, per i sistemi di IA ad alto rischio, un sistema di gestione dei rischi istituito, attuato, documentato e mantenuto [1]. Non è un adempimento una tantum: è un processo iterativo continuo, pianificato ed eseguito lungo l'intero ciclo di vita del sistema, con riesame e aggiornamento sistematici [2].\n\nIl processo comprende l'individuazione e l'analisi dei rischi noti e ragionevolmente prevedibili per salute, sicurezza e diritti fondamentali, la stima dei rischi legati all'uso conforme e all'uso improprio ragionevolmente prevedibile e l'adozione di misure adeguate. I sistemi sono sottoposti a prova per individuare le misure di gestione dei rischi più appropriate [3]. Per i sistemi dell'allegato III questi requisiti si applicano dal 2 dicembre 2027 [4].",
    citations: [
      {
        framework: 'AI_ACT',
        reference: 'art. 9, par. 1',
        quote_snippet: AI_ACT_ART9_QUOTE,
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'art. 9, par. 2',
        quote_snippet:
          "Il sistema di gestione dei rischi è inteso come un processo iterativo continuo pianificato ed eseguito nel corso dell'intero ciclo di vita di un sistema di IA ad alto rischio, che richiede un riesame e un aggiornamento costanti e sistematici.",
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'art. 9, par. 6',
        quote_snippet:
          'I sistemi di IA ad alto rischio sono sottoposti a prova al fine di individuare le misure di gestione dei rischi più appropriate e mirate.',
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'art. 113, terzo comma, lett. c), punto i)',
        quote_snippet: AI_ACT_ART113_ANNEX3_QUOTE,
        celex: '32024R1689',
        verified: true,
      },
    ],
    confidence_score: 0.93,
    requires_expert_review: false,
    related_frameworks: ['GDPR'],
    caveats: ['Le norme armonizzate preciseranno le modalità attuative.'],
  },
  gdpr: {
    answer:
      "Il Regolamento (UE) 2016/679 (GDPR) fissa i principi del trattamento dei dati personali. Il trattamento è lecito solo se ricorre almeno una base giuridica: consenso, contratto, obbligo legale, interessi vitali, interesse pubblico o legittimo interesse [1]. I dati devono essere adeguati, pertinenti e limitati a quanto necessario rispetto alle finalità [2].\n\nGli interessati hanno diritto di accesso, rettifica, cancellazione, limitazione, portabilità e opposizione (articoli da 15 a 21). In caso di violazione dei dati, il titolare la notifica all'autorità di controllo senza ingiustificato ritardo e, ove possibile, entro 72 ore [3]. La nomina di un responsabile della protezione dei dati è obbligatoria, tra l'altro, per le autorità e gli organismi pubblici e quando le attività principali comportano un monitoraggio regolare e sistematico su larga scala [4].\n\nLe sanzioni per le violazioni più gravi arrivano a 20 milioni di euro o al 4% del fatturato mondiale annuo, se superiore [5].",
    citations: [
      {
        framework: 'GDPR',
        reference: 'art. 6, par. 1',
        quote_snippet: 'Il trattamento è lecito solo se e nella misura in cui ricorre almeno una delle seguenti condizioni',
        celex: '32016R0679',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'art. 5, par. 1, lett. c)',
        quote_snippet:
          'adeguati, pertinenti e limitati a quanto necessario rispetto alle finalità per le quali sono trattati («minimizzazione dei dati»)',
        celex: '32016R0679',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'art. 33, par. 1',
        quote_snippet:
          "il titolare del trattamento notifica la violazione all'autorità di controllo competente a norma dell'articolo 55 senza ingiustificato ritardo e, ove possibile, entro 72 ore dal momento in cui ne è venuto a conoscenza",
        celex: '32016R0679',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'art. 37, par. 1',
        quote_snippet: GDPR_ART37_QUOTE,
        celex: '32016R0679',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'art. 83, par. 5',
        quote_snippet:
          "fino a 20 000 000 EUR, o per le imprese, fino al 4 % del fatturato mondiale totale annuo dell'esercizio precedente, se superiore",
        celex: '32016R0679',
        verified: true,
      },
    ],
    confidence_score: 0.94,
    requires_expert_review: false,
    related_frameworks: ['AI_ACT', 'NIS2'],
    caveats: [],
  },
  gdpr_art9: {
    answer:
      "L'articolo 9 del GDPR vieta di trattare dati personali che rivelino origine razziale o etnica, opinioni politiche, convinzioni religiose o filosofiche o appartenenza sindacale, e di trattare dati genetici, dati biometrici intesi a identificare in modo univoco una persona, dati sulla salute o sulla vita e sull'orientamento sessuale [1].\n\nIl divieto cade solo nei casi elencati dal paragrafo 2, tra cui il consenso esplicito dell'interessato per finalità specifiche [2], gli obblighi in materia di diritto del lavoro e sicurezza sociale, gli interessi vitali, i dati resi manifestamente pubblici, la difesa di un diritto in sede giudiziaria, i motivi di interesse pubblico rilevante e le finalità di medicina, sanità pubblica, archiviazione e ricerca.\n\nGli Stati membri possono introdurre condizioni ulteriori, anche limitazioni, per i dati genetici, biometrici e relativi alla salute [3].",
    citations: [
      {
        framework: 'GDPR',
        reference: 'art. 9, par. 1',
        quote_snippet:
          "È vietato trattare dati personali che rivelino l'origine razziale o etnica, le opinioni politiche, le convinzioni religiose o filosofiche, o l'appartenenza sindacale, nonché trattare dati genetici, dati biometrici intesi a identificare in modo univoco una persona fisica, dati relativi alla salute o alla vita sessuale o all'orientamento sessuale della persona.",
        celex: '32016R0679',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'art. 9, par. 2, lett. a)',
        quote_snippet:
          "l'interessato ha prestato il proprio consenso esplicito al trattamento di tali dati personali per una o più finalità specifiche",
        celex: '32016R0679',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'art. 9, par. 4',
        quote_snippet:
          'Gli Stati membri possono mantenere o introdurre ulteriori condizioni, comprese limitazioni, con riguardo al trattamento di dati genetici, dati biometrici o dati relativi alla salute.',
        celex: '32016R0679',
        verified: true,
      },
    ],
    confidence_score: 0.95,
    requires_expert_review: false,
    related_frameworks: ['AI_ACT'],
    caveats: ['Le eccezioni del paragrafo 2 vanno valutate caso per caso, con il responsabile della protezione dei dati.'],
  },
  gdpr_art13: {
    answer:
      "L'articolo 13 del GDPR elenca le informazioni che il titolare fornisce all'interessato nel momento in cui raccoglie i dati direttamente da lui [1]: identità e contatti del titolare e del responsabile della protezione dei dati, finalità e base giuridica, destinatari, eventuale trasferimento verso Paesi terzi. A queste si aggiungono le informazioni necessarie a un trattamento corretto e trasparente [2]: periodo di conservazione, diritti dell'interessato, diritto di reclamo all'autorità di controllo e, se esiste un processo decisionale automatizzato, la logica utilizzata e le conseguenze previste.\n\nL'informativa va data in forma concisa, trasparente, intelligibile e facilmente accessibile, con un linguaggio semplice e chiaro [3].",
    citations: [
      {
        framework: 'GDPR',
        reference: 'art. 13, par. 1',
        quote_snippet:
          "In caso di raccolta presso l'interessato di dati che lo riguardano, il titolare del trattamento fornisce all'interessato, nel momento in cui i dati personali sono ottenuti, le seguenti informazioni",
        celex: '32016R0679',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'art. 13, par. 2',
        quote_snippet:
          "fornisce all'interessato le seguenti ulteriori informazioni necessarie per garantire un trattamento corretto e trasparente",
        celex: '32016R0679',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'art. 12, par. 1',
        quote_snippet: 'in forma concisa, trasparente, intelligibile e facilmente accessibile, con un linguaggio semplice e chiaro',
        celex: '32016R0679',
        verified: true,
      },
    ],
    confidence_score: 0.95,
    requires_expert_review: false,
    related_frameworks: ['AI_ACT'],
    caveats: [],
  },
  gdpr_art17: {
    answer:
      "L'articolo 17 del GDPR dà all'interessato il diritto di ottenere dal titolare la cancellazione dei dati personali che lo riguardano senza ingiustificato ritardo [1], quando ricorre uno dei motivi previsti:\n\n1. i dati non sono più necessari rispetto alle finalità per cui erano stati raccolti;\n2. l'interessato revoca il consenso e non esiste altra base giuridica;\n3. l'interessato si oppone al trattamento e non prevale alcun motivo legittimo;\n4. i dati sono stati trattati illecitamente;\n5. la cancellazione è imposta da un obbligo legale dell'Unione o dello Stato membro.\n\nSe il titolare ha reso pubblici i dati, adotta misure ragionevoli per informare gli altri titolari che li trattano della richiesta di cancellazione [2]. Il diritto non si applica quando il trattamento è necessario per esercitare la libertà di espressione e di informazione, per adempiere un obbligo legale, per motivi di interesse pubblico in ambito sanitario, per fini di archiviazione o ricerca, o per accertare, esercitare o difendere un diritto in sede giudiziaria [3].",
    citations: [
      {
        framework: 'GDPR',
        reference: 'art. 17, par. 1',
        quote_snippet:
          "L'interessato ha il diritto di ottenere dal titolare del trattamento la cancellazione dei dati personali che lo riguardano senza ingiustificato ritardo",
        celex: '32016R0679',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'art. 17, par. 2',
        quote_snippet:
          "adotta le misure ragionevoli, anche tecniche, per informare i titolari del trattamento che stanno trattando i dati personali della richiesta dell'interessato di cancellare qualsiasi link, copia o riproduzione dei suoi dati personali",
        celex: '32016R0679',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'art. 17, par. 3, lett. a)',
        quote_snippet:
          "I paragrafi 1 e 2 non si applicano nella misura in cui il trattamento sia necessario: a) per l'esercizio del diritto alla libertà di espressione e di informazione",
        celex: '32016R0679',
        verified: true,
      },
    ],
    confidence_score: 0.95,
    requires_expert_review: false,
    related_frameworks: ['AI_ACT'],
    caveats: ['Le eccezioni del paragrafo 3 vanno valutate caso per caso, con il responsabile della protezione dei dati.'],
  },
  gdpr_dpo: {
    answer:
      "Il responsabile della protezione dei dati (DPO) va designato sistematicamente [1] quando il trattamento è svolto da un'autorità o un organismo pubblico, quando le attività principali richiedono un monitoraggio regolare e sistematico degli interessati su larga scala, oppure quando consistono nel trattamento su larga scala di categorie particolari di dati o di dati relativi a condanne penali.\n\nIl DPO è indipendente: non riceve istruzioni sull'esecuzione dei suoi compiti e non può essere rimosso o penalizzato per averli svolti [2]; riferisce al vertice gerarchico del titolare. I suoi compiti comprendono informare e consigliare il titolare e i dipendenti sugli obblighi in materia di protezione dei dati [3], sorvegliare l'osservanza del regolamento, fornire pareri sulla valutazione d'impatto e fungere da punto di contatto con l'autorità di controllo.",
    citations: [
      {
        framework: 'GDPR',
        reference: 'art. 37, par. 1',
        quote_snippet: GDPR_ART37_QUOTE,
        celex: '32016R0679',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'art. 38, par. 3',
        quote_snippet:
          "Il responsabile della protezione dei dati non è rimosso o penalizzato dal titolare del trattamento o dal responsabile del trattamento per l'adempimento dei propri compiti.",
        celex: '32016R0679',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'art. 39, par. 1, lett. a)',
        quote_snippet:
          'informare e fornire consulenza al titolare del trattamento o al responsabile del trattamento nonché ai dipendenti che eseguono il trattamento in merito agli obblighi derivanti dal presente regolamento',
        celex: '32016R0679',
        verified: true,
      },
    ],
    confidence_score: 0.95,
    requires_expert_review: false,
    related_frameworks: ['NIS2', 'AI_ACT'],
    caveats: ['Il regolamento non definisce «larga scala»: la valutazione va fatta sul caso concreto.'],
  },
  dora: {
    answer:
      "Il Regolamento (UE) 2022/2554 (DORA) si applica dal 17 gennaio 2025 [1] e impone alle entità finanziarie un quadro per la gestione dei rischi informatici solido, completo e documentato [2]. Gli incidenti gravi connessi alle TIC vanno segnalati all'autorità competente [3] con una notifica iniziale, una relazione intermedia e una relazione finale, nei termini fissati dalle norme tecniche di regolamentazione.\n\nLe entità individuate dalle autorità competenti, escluse le microimprese e quelle a regime semplificato, effettuano test di penetrazione guidati dalla minaccia (TLPT) almeno ogni tre anni [4]. Il rischio derivante dai fornitori terzi di servizi TIC va gestito come parte integrante del rischio informatico [5], con il contenuto contrattuale minimo dell'articolo 30: è da qui che nascono le richieste di banche e assicurazioni ai loro fornitori di software e servizi.",
    citations: [
      {
        framework: 'DORA',
        reference: 'art. 64',
        quote_snippet: 'Esso si applica a decorrere dal 17 gennaio 2025.',
        celex: '32022R2554',
        verified: true,
      },
      {
        framework: 'DORA',
        reference: 'art. 6, par. 1',
        quote_snippet: DORA_ART6_QUOTE,
        celex: '32022R2554',
        verified: true,
      },
      {
        framework: 'DORA',
        reference: 'art. 19, par. 1',
        quote_snippet: DORA_ART19_QUOTE,
        celex: '32022R2554',
        verified: true,
      },
      {
        framework: 'DORA',
        reference: 'art. 26, par. 1',
        quote_snippet: 'effettuano test avanzati sotto forma di test di penetrazione basati su minacce con cadenza almeno triennale',
        celex: '32022R2554',
        verified: true,
      },
      {
        framework: 'DORA',
        reference: 'art. 28, par. 1',
        quote_snippet: DORA_ART28_QUOTE,
        celex: '32022R2554',
        verified: true,
      },
    ],
    confidence_score: 0.92,
    requires_expert_review: false,
    related_frameworks: ['NIS2'],
    caveats: [
      "I termini di notifica degli incidenti sono fissati dalle norme tecniche di regolamentazione che integrano l'articolo 19, non dal regolamento.",
    ],
  },
  dora_art30: {
    answer:
      "L'articolo 30 di DORA fissa il contenuto minimo dei contratti con i fornitori terzi di servizi TIC. Ogni accordo contiene almeno [1]: la descrizione completa delle funzioni e dei servizi, le ubicazioni di trattamento e conservazione dei dati con preavviso in caso di cambiamento, le garanzie su disponibilità, integrità e riservatezza, l'assistenza in caso di incidente, i diritti di accesso, ispezione e audit, le condizioni di recesso e le strategie di uscita.\n\nQuando i servizi supportano funzioni essenziali o importanti si aggiungono elementi ulteriori [2]: livelli di servizio con obiettivi quantitativi e qualitativi, obblighi di notifica, partecipazione ai test di resilienza, condizioni per il subappalto. Il tutto rientra nella gestione del rischio informatico derivante da terzi, parte integrante del quadro di gestione dei rischi [3].",
    citations: [
      {
        framework: 'DORA',
        reference: 'art. 30, par. 2',
        quote_snippet: "Gli accordi contrattuali per l'utilizzo di servizi TIC comprendono almeno gli elementi seguenti",
        celex: '32022R2554',
        verified: true,
      },
      {
        framework: 'DORA',
        reference: 'art. 30, par. 3',
        quote_snippet:
          "Gli accordi contrattuali per l'utilizzo di servizi TIC a supporto di funzioni essenziali o importanti comprendono, in aggiunta agli elementi di cui al paragrafo 2, almeno quanto segue",
        celex: '32022R2554',
        verified: true,
      },
      {
        framework: 'DORA',
        reference: 'art. 28, par. 1',
        quote_snippet: DORA_ART28_QUOTE,
        celex: '32022R2554',
        verified: true,
      },
    ],
    confidence_score: 0.93,
    requires_expert_review: false,
    related_frameworks: ['NIS2'],
    caveats: ['Le norme tecniche di regolamentazione sulla politica per i fornitori TIC precisano i contenuti contrattuali.'],
  },
  nis2: {
    answer:
      "La Direttiva (UE) 2022/2555 (NIS2) si applica ai soggetti dei settori elencati negli allegati I e II che sono almeno medie imprese [1]. Per gli incidenti significativi prevede una notifica in tre tempi: un preallarme entro 24 ore dalla conoscenza dell'incidente [2], una notifica con la valutazione iniziale entro 72 ore [3] e una relazione finale entro un mese dalla notifica [4]. Un incidente è significativo quando ha causato o può causare una grave perturbazione operativa dei servizi o perdite finanziarie per il soggetto [5], oppure quando si è ripercosso o può ripercuotersi su altre persone causando perdite considerevoli.\n\nIn Italia la direttiva è recepita dal D.Lgs. 138/2024: le notifiche vanno al CSIRT Italia e i soggetti in ambito si registrano, o aggiornano la registrazione, sulla piattaforma dell'Agenzia per la cybersicurezza nazionale dal 1° gennaio al 28 febbraio di ogni anno [6].",
    citations: [
      {
        framework: 'NIS2',
        reference: 'art. 2, par. 1',
        quote_snippet:
          "La presente direttiva si applica ai soggetti pubblici o privati delle tipologie di cui all'allegato I o II che sono considerati medie imprese",
        celex: '32022L2555',
        verified: true,
      },
      {
        framework: 'NIS2',
        reference: 'art. 23, par. 4, lett. a)',
        quote_snippet: NIS2_ART23_4A_QUOTE,
        celex: '32022L2555',
        verified: true,
      },
      {
        framework: 'NIS2',
        reference: 'art. 23, par. 4, lett. b)',
        quote_snippet:
          "senza indebito ritardo, e comunque entro 72 ore da quando sono venuti a conoscenza dell'incidente significativo, una notifica dell'incidente",
        celex: '32022L2555',
        verified: true,
      },
      {
        framework: 'NIS2',
        reference: 'art. 23, par. 4, lett. d)',
        quote_snippet: "una relazione finale entro un mese dalla trasmissione della notifica dell'incidente di cui alla lettera b)",
        celex: '32022L2555',
        verified: true,
      },
      {
        framework: 'NIS2',
        reference: 'art. 23, par. 3',
        quote_snippet:
          'ha causato o è in grado di causare una grave perturbazione operativa dei servizi o perdite finanziarie per il soggetto interessato',
        celex: '32022L2555',
        verified: true,
      },
      {
        framework: 'IT',
        title: 'D.Lgs. 4 settembre 2024, n. 138',
        reference: 'art. 7, comma 1, e art. 25',
        quote_snippet: '',
        url: 'https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2024-09-04;138',
        verified: false,
      },
    ],
    confidence_score: 0.9,
    requires_expert_review: false,
    related_frameworks: ['DORA', 'GDPR'],
    caveats: [ITALIAN_LAW_CAVEAT],
  },
  taxonomy: {
    answer:
      "Il Regolamento (UE) 2020/852 (Tassonomia) stabilisce quando un'attività economica è ecosostenibile: deve contribuire in modo sostanziale ad almeno uno dei sei obiettivi ambientali, non arrecare un danno significativo agli altri, rispettare le garanzie minime di salvaguardia ed essere conforme ai criteri di vaglio tecnico [1]. I sei obiettivi sono la mitigazione e l'adattamento ai cambiamenti climatici, l'uso sostenibile delle acque e delle risorse marine, l'economia circolare, la prevenzione dell'inquinamento e la biodiversità [2].\n\nLe garanzie minime di salvaguardia sono procedure che assicurano l'allineamento con le linee guida OCSE per le imprese multinazionali e con i principi guida delle Nazioni Unite su imprese e diritti umani [3]. L'obbligo di pubblicare la quota di fatturato, investimenti e spese operative associata ad attività ecosostenibili riguarda le imprese soggette alla rendicontazione di sostenibilità [4]: dopo l'Omnibus I, quelle con più di 1.000 dipendenti e oltre 450 milioni di euro di ricavi netti.",
    citations: [
      {
        framework: 'TAXONOMY',
        reference: 'art. 3',
        quote_snippet:
          "un'attività economica è considerata ecosostenibile se: a) contribuisce in modo sostanziale al raggiungimento di uno o più degli obiettivi ambientali di cui all'articolo 9",
        celex: '32020R0852',
        verified: true,
      },
      {
        framework: 'TAXONOMY',
        reference: 'art. 9',
        quote_snippet:
          "a) la mitigazione dei cambiamenti climatici; b) l'adattamento ai cambiamenti climatici; c) l'uso sostenibile e la protezione delle acque e delle risorse marine; d) la transizione verso un'economia circolare; e) la prevenzione e la riduzione dell'inquinamento; f) la protezione e il ripristino della biodiversità e degli ecosistemi",
        celex: '32020R0852',
        verified: true,
      },
      {
        framework: 'TAXONOMY',
        reference: 'art. 18, par. 1',
        quote_snippet:
          "sono procedure attuate da un'impresa che svolge un'attività economica al fine di garantire che sia in linea con le linee guida OCSE destinate alle imprese multinazionali e con i Principi guida delle Nazioni Unite su imprese e diritti umani",
        celex: '32020R0852',
        verified: true,
      },
      {
        framework: 'TAXONOMY',
        reference: 'art. 8, par. 1',
        quote_snippet:
          "include, nella dichiarazione di carattere non finanziario o nella dichiarazione consolidata di carattere non finanziario, informazioni su come e in che misura le attività dell'impresa sono associate ad attività economiche considerate ecosostenibili",
        celex: '32020R0852',
        verified: true,
      },
    ],
    confidence_score: 0.88,
    requires_expert_review: false,
    related_frameworks: ['CSRD'],
    caveats: ['I criteri di vaglio tecnico sono negli atti delegati della Commissione e vengono aggiornati nel tempo.'],
  },
  cross_ai_gdpr: {
    answer:
      "Sotto l'AI Act: i sistemi di IA usati per valutare l'affidabilità creditizia delle persone fisiche o stabilirne il merito di credito sono ad alto rischio, salvo quelli usati per individuare frodi finanziarie [1]. Per questi sistemi è istituito un sistema di gestione dei rischi [2] e chi li usa (deployer) effettua, prima dell'uso, una valutazione dell'impatto sui diritti fondamentali [3]. I requisiti dell'alto rischio per i sistemi dell'allegato III si applicano dal 2 dicembre 2027 [4].\n\nSotto il GDPR: una decisione di credito presa unicamente in modo automatizzato ricade nell'articolo 22: l'interessato ha il diritto di non esservi sottoposto quando produce effetti giuridici o incide in modo analogo significativamente sulla sua persona [5], e una valutazione sistematica e globale di aspetti personali basata su trattamento automatizzato richiede una valutazione d'impatto sulla protezione dei dati [6].\n\nI due regimi si sommano: servono sia la valutazione d'impatto del GDPR sia quella sui diritti fondamentali dell'AI Act, che può rinviare alla prima per le parti già coperte (articolo 27, paragrafo 4).",
    citations: [
      {
        framework: 'AI_ACT',
        reference: 'allegato III, punto 5, lett. b)',
        quote_snippet:
          "i sistemi di IA destinati a essere utilizzati per valutare l'affidabilità creditizia delle persone fisiche o per stabilire il loro merito di credito, a eccezione dei sistemi di IA utilizzati allo scopo di individuare frodi finanziarie",
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'art. 9, par. 1',
        quote_snippet: AI_ACT_ART9_QUOTE,
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'art. 27, par. 1',
        quote_snippet: "effettuano una valutazione dell'impatto sui diritti fondamentali che l'uso di tale sistema può produrre",
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'art. 113, terzo comma, lett. c), punto i)',
        quote_snippet: AI_ACT_ART113_ANNEX3_QUOTE,
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'art. 22, par. 1',
        quote_snippet:
          "L'interessato ha il diritto di non essere sottoposto a una decisione basata unicamente sul trattamento automatizzato, compresa la profilazione, che produca effetti giuridici che lo riguardano o che incida in modo analogo significativamente sulla sua persona.",
        celex: '32016R0679',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'art. 35, par. 3, lett. a)',
        quote_snippet:
          'una valutazione sistematica e globale di aspetti personali relativi a persone fisiche, basata su un trattamento automatizzato, compresa la profilazione, e sulla quale si fondano decisioni che hanno effetti giuridici o incidono in modo analogo significativamente su dette persone fisiche',
        celex: '32016R0679',
        verified: true,
      },
    ],
    confidence_score: 0.89,
    requires_expert_review: false,
    related_frameworks: ['DORA'],
    caveats: ['Il coordinamento tra le due valutazioni va deciso sul caso concreto, con il responsabile della protezione dei dati.'],
  },
  cross_dora_nis2: {
    answer:
      "Sotto DORA: il Regolamento (UE) 2022/2554 è l'atto settoriale per la resilienza operativa digitale delle entità finanziarie: quadro di gestione dei rischi informatici [1], segnalazione degli incidenti gravi [2], test di resilienza e gestione dei fornitori terzi.\n\nSotto NIS2: la Direttiva (UE) 2022/2555 copre i soggetti essenziali e importanti con misure di gestione dei rischi e la notifica degli incidenti significativi in tre fasi (24 ore, 72 ore, un mese) [3].\n\nRapporto tra i due: quando un atto settoriale dell'Unione impone misure di gestione dei rischi o di notifica con effetto almeno equivalente, le disposizioni corrispondenti della NIS2 non si applicano a quei soggetti [4]; DORA è considerato un atto settoriale di questo tipo per le entità finanziarie [5]. Una banca applica quindi DORA per la gestione dei rischi e la notifica degli incidenti.",
    citations: [
      {
        framework: 'DORA',
        reference: 'art. 6, par. 1',
        quote_snippet: DORA_ART6_QUOTE,
        celex: '32022R2554',
        verified: true,
      },
      {
        framework: 'DORA',
        reference: 'art. 19, par. 1',
        quote_snippet: DORA_ART19_QUOTE,
        celex: '32022R2554',
        verified: true,
      },
      {
        framework: 'NIS2',
        reference: 'art. 23, par. 4, lett. a)',
        quote_snippet: NIS2_ART23_4A_QUOTE,
        celex: '32022L2555',
        verified: true,
      },
      {
        framework: 'NIS2',
        reference: 'art. 4, par. 1',
        quote_snippet:
          "a tali soggetti non si applicano le pertinenti disposizioni della presente direttiva, comprese le disposizioni relative alla vigilanza e all'esecuzione di cui al capo VII",
        celex: '32022L2555',
        verified: true,
      },
      {
        framework: 'DORA',
        reference: 'art. 1, par. 2',
        quote_snippet:
          "il presente regolamento è considerato un atto giuridico settoriale dell'Unione ai sensi dell'articolo 4 di tale direttiva",
        celex: '32022R2554',
        verified: true,
      },
    ],
    confidence_score: 0.92,
    requires_expert_review: false,
    related_frameworks: ['GDPR'],
    caveats: [],
  },
}

export const SUGGESTED_QUESTIONS_IT = [
  "La nostra società con 600 dipendenti rientra ancora nella CSRD dopo l'Omnibus?",
  "Un chatbot sul sito aziendale deve dichiarare di essere un'IA?",
  'Quali incidenti vanno notificati entro 24 ore secondo la NIS2?',
  "Dobbiamo formare i dipendenti che usano l'IA?",
]

export const NOT_COVERED_IT =
  'Questa domanda non rientra tra gli esempi della demo. Fuori dalla demo NormaAI cerca nei testi ufficiali del corpus e risponde con i passaggi di legge, oppure si astiene quando il testo non basta.'
