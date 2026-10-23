/**
 * Mock data for demo mode - allows full frontend usage without a running backend.
 * Each framework has dedicated, realistic mock responses.
 */

import type {
  User, TokenPair, QAResponse, GapAnalysisResponse,
  MonitorResponse, SystemStats, ComplianceStatus,
} from './types'

// ─── Auth Mocks ─────────────────────────────────────────────

export const DEMO_USER: User = {
  id: 'demo-user-001',
  email: 'demo@normaai.eu',
  name: 'Demo User',
  role: 'admin',
  organization_name: 'NormaAI Demo',
}

export const DEMO_TOKENS: TokenPair = {
  access_token: 'demo.jwt.token',
  refresh_token: 'demo.refresh.token',
  token_type: 'bearer',
  expires_in: 3600,
}

// ─── System Stats Mock ──────────────────────────────────────

export const DEMO_STATS: SystemStats = {
  status: 'healthy',
  version: '0.3.0',
  environment: 'demo',
  llm_provider: 'gemini',
  llm_model: 'gemini-2.5-flash-preview-05-20',
  timestamp: new Date().toISOString(),
  qdrant_available: true,
  llm_available: true,
  qdrant: {
    status: 'ok',
    points_count: 14823,
  },
  metrics: {
    total_requests: 1247,
    error_count: 0,
    endpoints: {
      'POST /api/v1/qa': { count: 532, avg_latency_ms: 1800, max_latency_ms: 5200 },
      'POST /api/v1/gap-analysis': { count: 189, avg_latency_ms: 3500, max_latency_ms: 8500 },
      'POST /api/v1/monitor': { count: 94, avg_latency_ms: 2400, max_latency_ms: 6800 },
      'GET /api/v1/stats': { count: 312, avg_latency_ms: 12, max_latency_ms: 45 },
      'GET /health': { count: 120, avg_latency_ms: 3, max_latency_ms: 8 },
    },
  },
}

// ─── Q&A Mocks ──────────────────────────────────────────────
//
// Demo answers for "Chiedi". They mirror what the real backend returns from
// POST /api/v1/qa, plus the optional fields the SSE citation events carry
// (verified, celex, url, article). Every quoted passage is the official
// Italian text on EUR-Lex; a citation to a text that is not yet in the
// corpus (the Omnibus I directive, the ESRS) is left unverified on purpose,
// so the demo shows the honest state too. Facts follow the public pages
// and ADR-003: CSRD after Omnibus I (Dir. (UE) 2026/470) applies above
// 1.000 employees AND 450 million euro net turnover; CSDDD transposition
// 2028-07-26 and first application 2029; AI Act art. 50 from 2026-08-02.

type DemoCitation = QAResponse['citations'][number] & {
  verified?: boolean
  celex?: string
  url?: string
  article?: string
  title?: string
}

export type DemoQAResponse = Omit<QAResponse, 'citations'> & {
  citations: DemoCitation[]
  abstention_reason?: string
  suggested_questions?: string[]
  /** Example corpus date of the demo (the real one travels in the response metadata). */
  corpus_as_of?: string
}

/** The example corpus date shown by the demo. Not a real corpus. */
export const DEMO_CORPUS_AS_OF = '2026-02-28'

const AI_ACT_ART50_QUOTE =
  'I fornitori garantiscono che i sistemi di IA destinati a interagire direttamente con le persone fisiche sono progettati e sviluppati in modo tale che le persone fisiche interessate siano informate del fatto che stanno interagendo con un sistema di IA'

const AI_ACT_ART9_QUOTE =
  'In relazione ai sistemi di IA ad alto rischio è istituito, attuato, documentato e mantenuto un sistema di gestione dei rischi.'

const CSRD_ART19A_QUOTE =
  "includono nella relazione sulla gestione le informazioni necessarie alla comprensione dell'impatto dell'impresa sulle questioni di sostenibilità, nonché le informazioni necessarie alla comprensione del modo in cui le questioni di sostenibilità influiscono sull'andamento dell'impresa, sui suoi risultati e sulla sua situazione"

const CSDDD_ART5_QUOTE =
  'Gli Stati membri provvedono affinché le società esercitino il dovere di diligenza in materia di diritti umani e di ambiente basato sul rischio di cui agli articoli da 7 a 16 («dovere di diligenza»)'

const DORA_ART6_QUOTE =
  'Le entità finanziarie dispongono di un quadro per la gestione dei rischi informatici solido, completo e ben documentato, che fa parte del loro sistema generale di gestione dei rischi'

const DORA_ART19_QUOTE =
  "Le entità finanziarie segnalano all'autorità competente pertinente di cui all'articolo 46 i gravi incidenti connessi alle TIC"

const NIS2_ART23_4A_QUOTE =
  "senza indebito ritardo, e comunque entro 24 ore dalla conoscenza dell'incidente significativo, un preallarme"

const OMNIBUS_NOT_IN_CORPUS =
  "Il testo della Direttiva (UE) 2026/470 (Omnibus I) non è ancora nel corpus: la citazione che la riguarda va verificata su EUR-Lex prima di decidere."

const QA_RESPONSES: Record<string, DemoQAResponse> = {
  csrd: {
    answer:
      "Dopo l'Omnibus I (Direttiva (UE) 2026/470, in vigore dal 18 marzo 2026) l'obbligo di rendicontazione di sostenibilità della CSRD riguarda solo le imprese che superano entrambe le soglie: più di 1.000 dipendenti in media nell'esercizio e un fatturato netto superiore a 450 milioni di euro [1]. Le due condizioni sono cumulative: non vale più il criterio «due su tre» previsto in origine dalla Direttiva (UE) 2022/2464.\n\nUn'impresa sotto una delle due soglie (per esempio 600 dipendenti, qualunque sia il fatturato) resta fuori dall'obbligo diretto. Le imprese ancora obbligate includono nella relazione sulla gestione le informazioni necessarie a comprendere il loro impatto sulle questioni di sostenibilità e il modo in cui queste influiscono sull'andamento dell'impresa [2]: è da questo obbligo che nascono le richieste di dati lungo la catena del valore, anche verso fornitori più piccoli.\n\nPer chi rientrava nella prima ondata (imprese già soggette alla direttiva sulle informazioni non finanziarie) l'Omnibus prevede un'esenzione transitoria per gli esercizi 2025 e 2026: verificate la vostra posizione sul testo consolidato.",
    citations: [
      {
        framework: 'CSRD',
        title: 'Direttiva (UE) 2026/470 (Omnibus I)',
        reference: "art. 1, nuove soglie dell'art. 19 bis della Direttiva 2013/34/UE",
        quote_snippet: '',
        celex: '32026L0470',
        verified: false,
      },
      {
        framework: 'CSRD',
        reference: 'art. 19 bis, par. 1, della Direttiva 2013/34/UE (inserito dalla Direttiva (UE) 2022/2464)',
        quote_snippet: CSRD_ART19A_QUOTE,
        celex: '32022L2464',
        verified: true,
      },
    ],
    confidence_score: 0.78,
    requires_expert_review: true,
    related_frameworks: ['CSDDD', 'TAXONOMY', 'ESRS'],
    caveats: [OMNIBUS_NOT_IN_CORPUS],
  },
  csddd: {
    answer:
      "La CSDDD (Direttiva (UE) 2024/1760) impone alle imprese più grandi un dovere di diligenza sui diritti umani e sull'ambiente lungo la catena di attività: integrarlo nelle politiche aziendali, individuare e valutare gli impatti negativi effettivi e potenziali, prevenirli o farli cessare e renderne conto [1]. Le imprese devono anche dare alle persone e alle organizzazioni interessate la possibilità di presentare reclami [2].\n\nL'Omnibus I (Direttiva (UE) 2026/470) ha riscritto calendario e perimetro: il recepimento negli Stati membri è dovuto entro il 26 luglio 2028 e la prima applicazione alle imprese scatta nel 2029 [3]. Lo stesso atto ha ristretto l'ambito soggettivo, eliminato l'obbligo di adottare un piano di transizione climatica e rimosso il regime armonizzato di responsabilità civile.\n\nPrima di pianificare, verificate le soglie sul testo consolidato: gli orientamenti della Commissione sono attesi per luglio 2027.",
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
        reference: 'art. 14, par. 1',
        quote_snippet: 'la possibilità di presentare loro reclami qualora nutrano legittime preoccupazioni riguardo agli impatti negativi effettivi o potenziali',
        celex: '32024L1760',
        verified: true,
      },
      {
        framework: 'CSDDD',
        title: 'Direttiva (UE) 2026/470 (Omnibus I)',
        reference: "modifiche all'art. 37 della Direttiva (UE) 2024/1760 (recepimento e applicazione)",
        quote_snippet: '',
        celex: '32026L0470',
        verified: false,
      },
    ],
    confidence_score: 0.8,
    requires_expert_review: true,
    related_frameworks: ['CSRD', 'TAXONOMY'],
    caveats: [OMNIBUS_NOT_IN_CORPUS],
  },
  ai_act: {
    answer:
      "Il Regolamento (UE) 2024/1689 (AI Act) gradua gli obblighi in base al rischio. Alcune pratiche sono vietate, per esempio i sistemi che usano tecniche subliminali o manipolative per distorcere il comportamento delle persone [1]. Sono ad alto rischio i sistemi elencati nell'allegato III (tra cui valutazione del merito di credito, selezione del personale, infrastrutture critiche) e quelli che sono componenti di sicurezza di prodotti regolamentati [2]: per questi il fornitore istituisce un sistema di gestione dei rischi [3], oltre a governance dei dati, documentazione tecnica, trasparenza e sorveglianza umana.\n\nPer i sistemi destinati a interagire con le persone valgono gli obblighi di trasparenza dell'articolo 50: chi fornisce un chatbot lo progetta in modo che le persone sappiano di parlare con un'IA [4]. Il regolamento si applica dal 2 agosto 2026 [5]. Le sanzioni per le pratiche vietate arrivano a 35 milioni di euro o al 7% del fatturato mondiale annuo, se superiore [6].",
    citations: [
      {
        framework: 'AI_ACT',
        reference: 'art. 5, par. 1, lett. a)',
        quote_snippet: "l'immissione sul mercato, la messa in servizio o l'uso di un sistema di IA che utilizza tecniche subliminali che agiscono senza che una persona ne sia consapevole o tecniche volutamente manipolative o ingannevoli",
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'art. 6, par. 2',
        quote_snippet: "Oltre ai sistemi di IA ad alto rischio di cui al paragrafo 1, sono considerati ad alto rischio anche i sistemi di IA di cui all'allegato III.",
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
        reference: 'art. 50, par. 1',
        quote_snippet: AI_ACT_ART50_QUOTE,
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'art. 113',
        quote_snippet: 'Esso si applica a decorrere dal 2 agosto 2026.',
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'art. 99, par. 3',
        quote_snippet: "La non conformità al divieto delle pratiche di IA di cui all'articolo 5 è soggetta a sanzioni amministrative pecuniarie fino a 35 000 000 EUR o, se l'autore del reato è un'impresa, fino al 7 % del fatturato mondiale totale annuo dell'esercizio precedente, se superiore.",
        celex: '32024R1689',
        verified: true,
      },
    ],
    confidence_score: 0.93,
    requires_expert_review: false,
    related_frameworks: ['GDPR', 'DORA'],
    caveats: [
      "L'applicazione degli obblighi per i sistemi ad alto rischio dell'allegato III è stata rinviata al 2 dicembre 2027 dal pacchetto Omnibus digitale: verificate il calendario aggiornato prima di pianificare.",
    ],
  },
  ai_act_art50: {
    answer:
      "Sì. L'articolo 50, paragrafo 1, del Regolamento (UE) 2024/1689 obbliga chi fornisce un sistema di IA destinato a interagire direttamente con le persone a progettarlo in modo che le persone sappiano di parlare con un'IA, salvo che sia evidente dal contesto per una persona ragionevolmente informata, attenta e avveduta [1]. Per un assistente virtuale sul sito aziendale la via più semplice è una dichiarazione esplicita all'avvio della conversazione.\n\nL'obbligo si applica dal 2 agosto 2026 [2]. Se l'assistente genera testi, audio o immagini sintetiche valgono anche gli obblighi di marcatura dei contenuti artificiali previsti dallo stesso articolo. Le sanzioni per la violazione degli obblighi di trasparenza arrivano a 15 milioni di euro o al 3% del fatturato mondiale annuo, se superiore [3]; per le PMI e le start-up si applica il minore dei due importi.",
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
        reference: 'art. 113',
        quote_snippet: 'Esso si applica a decorrere dal 2 agosto 2026.',
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'art. 99, par. 4',
        quote_snippet: "è soggetta a sanzioni amministrative pecuniarie fino a 15 000 000 EUR o, se l'autore del reato è un'impresa, fino al 3 % del fatturato mondiale totale annuo dell'esercizio precedente, se superiore",
        celex: '32024R1689',
        verified: true,
      },
    ],
    confidence_score: 0.94,
    requires_expert_review: false,
    related_frameworks: ['GDPR'],
    caveats: [],
  },
  gdpr: {
    answer:
      "Il Regolamento (UE) 2016/679 (GDPR) fissa i principi del trattamento dei dati personali. Il trattamento è lecito solo se ricorre almeno una base giuridica: consenso, contratto, obbligo legale, interessi vitali, interesse pubblico o legittimo interesse [1]. I dati devono essere adeguati, pertinenti e limitati a quanto necessario rispetto alle finalità [2].\n\nGli interessati hanno diritto di accesso, rettifica, cancellazione, portabilità e opposizione (articoli da 15 a 21). In caso di violazione dei dati, il titolare notifica l'autorità di controllo senza ingiustificato ritardo e, ove possibile, entro 72 ore [3]. La nomina di un responsabile della protezione dei dati è obbligatoria, tra l'altro, per le autorità e gli organismi pubblici e quando le attività principali comportano un monitoraggio regolare e sistematico su larga scala [4].\n\nLe sanzioni per le violazioni più gravi arrivano a 20 milioni di euro o al 4% del fatturato mondiale annuo, se superiore [5].",
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
        quote_snippet: 'adeguati, pertinenti e limitati a quanto necessario rispetto alle finalità per le quali sono trattati («minimizzazione dei dati»)',
        celex: '32016R0679',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'art. 33, par. 1',
        quote_snippet: "il titolare del trattamento notifica la violazione all'autorità di controllo competente a norma dell'articolo 55 senza ingiustificato ritardo e, ove possibile, entro 72 ore dal momento in cui ne è venuto a conoscenza",
        celex: '32016R0679',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'art. 37, par. 1',
        quote_snippet: 'Il titolare del trattamento e il responsabile del trattamento designano sistematicamente un responsabile della protezione dei dati ogniqualvolta',
        celex: '32016R0679',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'art. 83, par. 5',
        quote_snippet: "fino a 20 000 000 EUR, o per le imprese, fino al 4 % del fatturato mondiale totale annuo dell'esercizio precedente, se superiore",
        celex: '32016R0679',
        verified: true,
      },
    ],
    confidence_score: 0.94,
    requires_expert_review: false,
    related_frameworks: ['AI_ACT', 'NIS2'],
    caveats: [],
  },
  dora: {
    answer:
      "Il Regolamento (UE) 2022/2554 (DORA) si applica dal 17 gennaio 2025 [1] e impone alle entità finanziarie un quadro per la gestione dei rischi informatici solido, completo e documentato [2]. Gli incidenti gravi connessi alle TIC vanno segnalati all'autorità competente [3] con una notifica iniziale, una relazione intermedia e una relazione finale, nei termini fissati dalle norme tecniche di regolamentazione.\n\nLe entità diverse dalle microimprese e da quelle a regime semplificato effettuano test avanzati di penetrazione guidati dalla minaccia (TLPT) almeno ogni tre anni [4]. Il rischio derivante dai fornitori terzi di servizi TIC va gestito come parte integrante del rischio informatico, con clausole contrattuali minime obbligatorie [5].",
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
        quote_snippet: 'effettuano test avanzati mediante TLPT almeno ogni tre anni',
        celex: '32022R2554',
        verified: true,
      },
      {
        framework: 'DORA',
        reference: 'art. 28, par. 1',
        quote_snippet: "Le entità finanziarie gestiscono i rischi informatici derivanti da terzi come parte integrante dei rischi informatici nell'ambito del quadro per la gestione dei rischi informatici",
        celex: '32022R2554',
        verified: true,
      },
    ],
    confidence_score: 0.92,
    requires_expert_review: false,
    related_frameworks: ['NIS2'],
    caveats: [
      "I termini di notifica degli incidenti (notifica iniziale, relazione intermedia e relazione finale) sono fissati dalle norme tecniche di regolamentazione che integrano l'articolo 19, non dal regolamento.",
    ],
  },
  nis2: {
    answer:
      "La Direttiva (UE) 2022/2555 (NIS2) prevede per i soggetti essenziali e importanti una notifica degli incidenti significativi in tre tempi: un preallarme entro 24 ore dalla conoscenza dell'incidente [1], una notifica con la valutazione iniziale di gravità e impatto entro 72 ore [2] e una relazione finale entro un mese dalla notifica [3].\n\nUn incidente è significativo quando ha causato o può causare una grave perturbazione operativa dei servizi o perdite finanziarie per il soggetto, oppure quando si è ripercosso o può ripercuotersi su altre persone causando perdite considerevoli [4]. In Italia la direttiva è recepita dal D.Lgs. 138/2024.",
    citations: [
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
        quote_snippet: "senza indebito ritardo, e comunque entro 72 ore dalla conoscenza dell'incidente significativo, una notifica dell'incidente",
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
        quote_snippet: 'ha causato o è in grado di causare una grave perturbazione operativa dei servizi o perdite finanziarie per il soggetto interessato',
        celex: '32022L2555',
        verified: true,
      },
    ],
    confidence_score: 0.9,
    requires_expert_review: false,
    related_frameworks: ['DORA', 'GDPR'],
    caveats: ['I termini possono essere precisati dalla normativa nazionale di recepimento.'],
  },
  taxonomy: {
    answer:
      "Il Regolamento (UE) 2020/852 (Tassonomia) stabilisce quando un'attività economica è ecosostenibile: deve contribuire in modo sostanziale ad almeno uno dei sei obiettivi ambientali, non arrecare un danno significativo agli altri, rispettare le garanzie minime di salvaguardia ed essere conforme ai criteri di vaglio tecnico [1]. I sei obiettivi sono la mitigazione e l'adattamento ai cambiamenti climatici, l'uso sostenibile delle acque e delle risorse marine, l'economia circolare, la prevenzione dell'inquinamento e la biodiversità [2].\n\nLe garanzie minime di salvaguardia sono procedure che assicurano l'allineamento con le linee guida OCSE per le imprese multinazionali e con i principi guida delle Nazioni Unite su imprese e diritti umani [3]. Le imprese soggette alla rendicontazione di sostenibilità pubblicano la quota di fatturato, investimenti e spese operative associata ad attività ecosostenibili [4].",
    citations: [
      {
        framework: 'TAXONOMY',
        reference: 'art. 3',
        quote_snippet: "un'attività economica è considerata ecosostenibile se: a) contribuisce in modo sostanziale al raggiungimento di uno o più degli obiettivi ambientali di cui all'articolo 9",
        celex: '32020R0852',
        verified: true,
      },
      {
        framework: 'TAXONOMY',
        reference: 'art. 9',
        quote_snippet: "a) la mitigazione dei cambiamenti climatici; b) l'adattamento ai cambiamenti climatici; c) l'uso sostenibile e la protezione delle acque e delle risorse marine; d) la transizione verso un'economia circolare; e) la prevenzione e la riduzione dell'inquinamento; f) la protezione e il ripristino della biodiversità e degli ecosistemi",
        celex: '32020R0852',
        verified: true,
      },
      {
        framework: 'TAXONOMY',
        reference: 'art. 18, par. 1',
        quote_snippet: "sono procedure attuate da un'impresa che svolge un'attività economica al fine di garantire l'allineamento con le linee guida OCSE destinate alle imprese multinazionali e con i principi guida delle Nazioni Unite su imprese e diritti umani",
        celex: '32020R0852',
        verified: true,
      },
      {
        framework: 'TAXONOMY',
        reference: 'art. 8, par. 1',
        quote_snippet: "includono nella dichiarazione di carattere non finanziario o nella dichiarazione consolidata di carattere non finanziario informazioni su come e in che misura le attività dell'impresa sono associate ad attività economiche considerate ecosostenibili",
        celex: '32020R0852',
        verified: true,
      },
    ],
    confidence_score: 0.88,
    requires_expert_review: false,
    related_frameworks: ['CSRD', 'CSDDD'],
    caveats: ['I criteri di vaglio tecnico sono negli atti delegati della Commissione e vengono aggiornati nel tempo.'],
  },
  cross_ai_gdpr: {
    answer:
      "Sotto l'AI Act: i sistemi di IA usati per valutare l'affidabilità creditizia delle persone fisiche o stabilirne il merito di credito sono ad alto rischio, salvo quelli usati per individuare frodi finanziarie [1]. Il fornitore istituisce un sistema di gestione dei rischi [2]; il deployer, se è un ente creditizio, effettua prima dell'uso una valutazione dell'impatto sui diritti fondamentali [3].\n\nSotto il GDPR: una decisione di credito presa unicamente in modo automatizzato ricade nell'articolo 22: l'interessato ha il diritto di non esservi sottoposto quando produce effetti giuridici o incide in modo analogo significativamente sulla sua persona [4], e una valutazione sistematica e globale di aspetti personali basata su trattamento automatizzato richiede una valutazione d'impatto sulla protezione dei dati [5].\n\nI due regimi si sommano: servono sia la valutazione d'impatto GDPR sia quella sui diritti fondamentali dell'AI Act, e la sorveglianza umana richiesta dall'AI Act va coordinata con l'intervento umano previsto dall'articolo 22 del GDPR.",
    citations: [
      {
        framework: 'AI_ACT',
        reference: 'allegato III, punto 5, lett. b)',
        quote_snippet: "i sistemi di IA destinati a essere utilizzati per valutare l'affidabilità creditizia delle persone fisiche o per stabilire il loro merito di credito, a eccezione dei sistemi di IA utilizzati allo scopo di individuare frodi finanziarie",
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
        framework: 'GDPR',
        reference: 'art. 22, par. 1',
        quote_snippet: "L'interessato ha il diritto di non essere sottoposto a una decisione basata unicamente sul trattamento automatizzato, compresa la profilazione, che produca effetti giuridici che lo riguardano o che incida in modo analogo significativamente sulla sua persona.",
        celex: '32016R0679',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'art. 35, par. 3, lett. a)',
        quote_snippet: 'una valutazione sistematica e globale di aspetti personali relativi a persone fisiche, basata su un trattamento automatizzato, compresa la profilazione, e sulla quale si fondano decisioni che hanno effetti giuridici o incidono in modo analogo significativamente su dette persone fisiche',
        celex: '32016R0679',
        verified: true,
      },
    ],
    confidence_score: 0.89,
    requires_expert_review: false,
    related_frameworks: ['DORA'],
    caveats: ["Gli orientamenti dell'AI Office e dell'EDPB sul rapporto tra AI Act e GDPR nel credit scoring sono in evoluzione."],
  },
  cross_dora_nis2: {
    answer:
      "Sotto DORA: il Regolamento (UE) 2022/2554 è l'atto settoriale per la resilienza operativa digitale delle entità finanziarie: quadro di gestione dei rischi informatici [1], segnalazione degli incidenti gravi [2], test TLPT e gestione dei fornitori terzi.\n\nSotto NIS2: la Direttiva (UE) 2022/2555 copre i soggetti essenziali e importanti con misure di gestione dei rischi e la notifica degli incidenti significativi in tre fasi (24 ore, 72 ore, un mese) [3].\n\nRapporto tra i due: quando un atto settoriale dell'Unione impone misure di gestione dei rischi o di notifica con effetto almeno equivalente, le disposizioni corrispondenti della NIS2 non si applicano a quei soggetti [4]; DORA è considerato un atto settoriale di questo tipo per le entità finanziarie che rientrano in NIS2 [5]. Un'entità finanziaria che opera anche in un settore NIS2 non coperto da DORA può restare soggetta a entrambi.",
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
        quote_snippet: "le pertinenti disposizioni della presente direttiva, comprese le disposizioni relative alla vigilanza e all'esecuzione di cui al capo VII, non si applicano a tali soggetti",
        celex: '32022L2555',
        verified: true,
      },
      {
        framework: 'DORA',
        reference: 'art. 1, par. 2',
        quote_snippet: "il presente regolamento è considerato un atto giuridico settoriale dell'Unione ai fini dell'articolo 4 di detta direttiva",
        celex: '32022R2554',
        verified: true,
      },
    ],
    confidence_score: 0.92,
    requires_expert_review: false,
    related_frameworks: ['GDPR'],
    caveats: ["La valutazione dell'effetto «almeno equivalente» spetta alle autorità nazionali, caso per caso."],
  },
  // ─── Article-specific responses ──────────────────────────
  gdpr_art17: {
    answer:
      "L'articolo 17 del GDPR dà all'interessato il diritto di ottenere dal titolare la cancellazione dei dati personali che lo riguardano senza ingiustificato ritardo [1], quando ricorre uno dei motivi previsti:\n\n1. i dati non sono più necessari rispetto alle finalità per cui erano stati raccolti;\n2. l'interessato revoca il consenso e non esiste altra base giuridica;\n3. l'interessato si oppone al trattamento e non prevale alcun motivo legittimo;\n4. i dati sono stati trattati illecitamente;\n5. la cancellazione è imposta da un obbligo legale dell'Unione o dello Stato membro.\n\nSe il titolare ha reso pubblici i dati, adotta misure ragionevoli per informare gli altri titolari che li trattano della richiesta di cancellazione [2]. Il diritto non si applica quando il trattamento è necessario per esercitare la libertà di espressione e di informazione, per adempiere un obbligo legale, per motivi di interesse pubblico in ambito sanitario, per fini di archiviazione o ricerca, o per accertare, esercitare o difendere un diritto in sede giudiziaria [3].",
    citations: [
      {
        framework: 'GDPR',
        reference: 'art. 17, par. 1',
        quote_snippet: "L'interessato ha il diritto di ottenere dal titolare del trattamento la cancellazione dei dati personali che lo riguardano senza ingiustificato ritardo",
        celex: '32016R0679',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'art. 17, par. 2',
        quote_snippet: "adotta le misure ragionevoli, anche tecniche, per informare i titolari del trattamento che stanno trattando i dati personali della richiesta dell'interessato di cancellare qualsiasi link, copia o riproduzione dei suoi dati personali",
        celex: '32016R0679',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'art. 17, par. 3, lett. a)',
        quote_snippet: "I paragrafi 1 e 2 non si applicano nella misura in cui il trattamento sia necessario: a) per l'esercizio del diritto alla libertà di espressione e di informazione",
        celex: '32016R0679',
        verified: true,
      },
    ],
    confidence_score: 0.95,
    requires_expert_review: false,
    related_frameworks: ['AI_ACT'],
    caveats: ['Le eccezioni del paragrafo 3 vanno valutate caso per caso, con il supporto del responsabile della protezione dei dati.'],
  },
  gdpr_art13: {
    answer:
      "L'articolo 13 del GDPR elenca le informazioni che il titolare fornisce all'interessato nel momento in cui raccoglie i dati direttamente da lui [1]: identità e contatti del titolare e del responsabile della protezione dei dati, finalità e base giuridica, destinatari, eventuale trasferimento verso Paesi terzi. A queste si aggiungono le informazioni necessarie a un trattamento corretto e trasparente [2]: periodo di conservazione, diritti dell'interessato, diritto di reclamo all'autorità di controllo e, se esiste un processo decisionale automatizzato, la logica utilizzata e le conseguenze previste.\n\nL'informativa va data in forma concisa, trasparente, intelligibile e facilmente accessibile, con un linguaggio semplice e chiaro [3].",
    citations: [
      {
        framework: 'GDPR',
        reference: 'art. 13, par. 1',
        quote_snippet: "In caso di raccolta presso l'interessato di dati che lo riguardano, il titolare del trattamento fornisce all'interessato, nel momento in cui i dati personali sono ottenuti, le seguenti informazioni",
        celex: '32016R0679',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'art. 13, par. 2',
        quote_snippet: "fornisce all'interessato le seguenti ulteriori informazioni necessarie per garantire un trattamento corretto e trasparente",
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
  ai_act_art9: {
    answer:
      "L'articolo 9 dell'AI Act impone, per i sistemi di IA ad alto rischio, un sistema di gestione dei rischi istituito, attuato, documentato e mantenuto [1]. Non è un adempimento una tantum: è un processo iterativo continuo, pianificato ed eseguito lungo l'intero ciclo di vita del sistema, con riesame e aggiornamento sistematici [2].\n\nIl processo comprende l'individuazione e l'analisi dei rischi noti e ragionevolmente prevedibili per salute, sicurezza e diritti fondamentali, la stima dei rischi legati all'uso conforme e all'uso improprio ragionevolmente prevedibile e l'adozione di misure adeguate. I sistemi sono sottoposti a prova per individuare le misure di gestione dei rischi più appropriate [3].",
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
        quote_snippet: "Il sistema di gestione dei rischi è inteso come un processo iterativo continuo pianificato ed eseguito nel corso dell'intero ciclo di vita di un sistema di IA ad alto rischio, che richiede un riesame e un aggiornamento sistematici periodici.",
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'art. 9, par. 5',
        quote_snippet: 'I sistemi di IA ad alto rischio sono sottoposti a prova al fine di individuare le misure di gestione dei rischi più appropriate e mirate.',
        celex: '32024R1689',
        verified: true,
      },
    ],
    confidence_score: 0.93,
    requires_expert_review: false,
    related_frameworks: ['GDPR'],
    caveats: ["Le norme armonizzate e gli orientamenti dell'AI Office preciseranno le modalità attuative."],
  },
  gdpr_art9: {
    answer:
      "L'articolo 9 del GDPR vieta di trattare dati personali che rivelino origine razziale o etnica, opinioni politiche, convinzioni religiose o filosofiche o appartenenza sindacale, e di trattare dati genetici, dati biometrici intesi a identificare in modo univoco una persona, dati sulla salute o sulla vita e sull'orientamento sessuale [1].\n\nIl divieto cade solo nei casi elencati dal paragrafo 2, tra cui il consenso esplicito dell'interessato per finalità specifiche [2], gli obblighi in materia di diritto del lavoro e sicurezza sociale, gli interessi vitali, i dati resi manifestamente pubblici, la difesa di un diritto in sede giudiziaria, i motivi di interesse pubblico rilevante e le finalità di medicina, sanità pubblica, archiviazione e ricerca.\n\nGli Stati membri possono introdurre condizioni ulteriori, anche limitazioni, per i dati genetici, biometrici e relativi alla salute [3].",
    citations: [
      {
        framework: 'GDPR',
        reference: 'art. 9, par. 1',
        quote_snippet: "È vietato trattare dati personali che rivelino l'origine razziale o etnica, le opinioni politiche, le convinzioni religiose o filosofiche, o l'appartenenza sindacale, nonché trattare dati genetici, dati biometrici intesi a identificare in modo univoco una persona fisica, dati relativi alla salute o alla vita sessuale o all'orientamento sessuale della persona.",
        celex: '32016R0679',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'art. 9, par. 2, lett. a)',
        quote_snippet: "l'interessato ha prestato il proprio consenso esplicito al trattamento di tali dati personali per una o più finalità specifiche",
        celex: '32016R0679',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'art. 9, par. 4',
        quote_snippet: 'Gli Stati membri possono mantenere o introdurre ulteriori condizioni, comprese limitazioni, con riguardo al trattamento di dati genetici, dati biometrici o dati relativi alla salute.',
        celex: '32016R0679',
        verified: true,
      },
    ],
    confidence_score: 0.95,
    requires_expert_review: false,
    related_frameworks: ['AI_ACT'],
    caveats: ['Le eccezioni del paragrafo 2 vanno valutate caso per caso: coinvolgete il responsabile della protezione dei dati.'],
  },
  dora_art30: {
    answer:
      "L'articolo 30 di DORA fissa il contenuto minimo dei contratti con i fornitori terzi di servizi TIC. Ogni accordo contiene almeno [1]: la descrizione completa delle funzioni e dei servizi, le ubicazioni di trattamento e conservazione dei dati con preavviso in caso di cambiamento, le garanzie su disponibilità, integrità e riservatezza, l'assistenza in caso di incidente, i diritti di accesso, ispezione e audit, le condizioni di recesso e le strategie di uscita.\n\nQuando i servizi supportano funzioni essenziali o importanti si aggiungono elementi ulteriori [2]: livelli di servizio con obiettivi quantitativi e qualitativi, obblighi di notifica, partecipazione ai test di resilienza, condizioni per il subappalto. Il tutto rientra nella gestione del rischio informatico derivante da terzi, parte integrante del quadro di gestione dei rischi [3].",
    citations: [
      {
        framework: 'DORA',
        reference: 'art. 30, par. 2',
        quote_snippet: "Gli accordi contrattuali relativi all'uso di servizi TIC comprendono almeno gli elementi seguenti",
        celex: '32022R2554',
        verified: true,
      },
      {
        framework: 'DORA',
        reference: 'art. 30, par. 3',
        quote_snippet: "Gli accordi contrattuali relativi all'uso di servizi TIC a supporto di funzioni essenziali o importanti comprendono, oltre agli elementi di cui al paragrafo 2, almeno gli elementi seguenti",
        celex: '32022R2554',
        verified: true,
      },
      {
        framework: 'DORA',
        reference: 'art. 28, par. 1',
        quote_snippet: "Le entità finanziarie gestiscono i rischi informatici derivanti da terzi come parte integrante dei rischi informatici nell'ambito del quadro per la gestione dei rischi informatici",
        celex: '32022R2554',
        verified: true,
      },
    ],
    confidence_score: 0.93,
    requires_expert_review: false,
    related_frameworks: ['NIS2'],
    caveats: ['Le norme tecniche di regolamentazione sulla politica per i fornitori TIC precisano i contenuti contrattuali.'],
  },
  gdpr_dpo: {
    answer:
      "Il responsabile della protezione dei dati (DPO) va designato sistematicamente [1] quando il trattamento è svolto da un'autorità o un organismo pubblico, quando le attività principali richiedono un monitoraggio regolare e sistematico degli interessati su larga scala, oppure quando consistono nel trattamento su larga scala di categorie particolari di dati o di dati relativi a condanne penali.\n\nIl DPO è indipendente: non riceve istruzioni sull'esecuzione dei suoi compiti e non può essere rimosso o penalizzato per averli svolti [2]; riferisce al vertice gerarchico del titolare. I suoi compiti comprendono informare e consigliare il titolare e i dipendenti sugli obblighi in materia di protezione dei dati [3], sorvegliare l'osservanza del regolamento, fornire pareri sulla valutazione d'impatto e fungere da punto di contatto con l'autorità di controllo.",
    citations: [
      {
        framework: 'GDPR',
        reference: 'art. 37, par. 1',
        quote_snippet: 'Il titolare del trattamento e il responsabile del trattamento designano sistematicamente un responsabile della protezione dei dati ogniqualvolta',
        celex: '32016R0679',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'art. 38, par. 3',
        quote_snippet: "Il responsabile della protezione dei dati non è rimosso o penalizzato dal titolare del trattamento o dal responsabile del trattamento per l'adempimento dei propri compiti.",
        celex: '32016R0679',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'art. 39, par. 1, lett. a)',
        quote_snippet: 'informare e fornire consulenza al titolare del trattamento o al responsabile del trattamento nonché ai dipendenti che eseguono il trattamento in merito agli obblighi derivanti dal presente regolamento',
        celex: '32016R0679',
        verified: true,
      },
    ],
    confidence_score: 0.95,
    requires_expert_review: false,
    related_frameworks: ['NIS2', 'AI_ACT'],
    caveats: ["Le linee guida dell'EDPB (già WP29, WP243) precisano i criteri di «larga scala» e «monitoraggio regolare e sistematico»."],
  },
  cross_csrd_csddd: {
    answer:
      "Sotto la CSRD: le imprese obbligate includono nella relazione sulla gestione le informazioni necessarie a comprendere il loro impatto sulle questioni di sostenibilità [1]; gli ESRS (Regolamento delegato (UE) 2023/2772) precisano le metriche e, per il clima, richiedono di comunicare le emissioni lorde di gas serra di ambito 1, 2 e 3 [2]: le emissioni della catena del valore entrano quindi nel reporting.\n\nSotto la CSDDD: il dovere di diligenza richiede di integrare la diligenza nelle politiche, individuare e valutare gli impatti negativi effettivi e potenziali lungo la catena di attività, prevenirli o farli cessare [3]. Dopo l'Omnibus I la prima applicazione è prevista nel 2029 [4].\n\nInsieme: la mappatura della catena di attività fatta per la CSDDD alimenta il calcolo dell'ambito 3 richiesto dagli ESRS; conviene costruire un unico processo di raccolta dati sui fornitori che serva entrambi gli obblighi.",
    citations: [
      {
        framework: 'CSRD',
        reference: 'art. 19 bis, par. 1, della Direttiva 2013/34/UE (inserito dalla Direttiva (UE) 2022/2464)',
        quote_snippet: CSRD_ART19A_QUOTE,
        celex: '32022L2464',
        verified: true,
      },
      {
        framework: 'ESRS',
        reference: 'ESRS E1-6, par. 44',
        quote_snippet: '',
        celex: '32023R2772',
        verified: false,
      },
      {
        framework: 'CSDDD',
        reference: 'art. 5, par. 1',
        quote_snippet: CSDDD_ART5_QUOTE,
        celex: '32024L1760',
        verified: true,
      },
      {
        framework: 'CSDDD',
        title: 'Direttiva (UE) 2026/470 (Omnibus I)',
        reference: "modifiche all'art. 37 della Direttiva (UE) 2024/1760 (recepimento e applicazione)",
        quote_snippet: '',
        celex: '32026L0470',
        verified: false,
      },
    ],
    confidence_score: 0.8,
    requires_expert_review: true,
    related_frameworks: ['TAXONOMY'],
    caveats: ['Le citazioni [2] e [4] non sono ancora verificate nel corpus: controllatele su EUR-Lex prima di decidere.'],
  },
}

const DEMO_SUGGESTED_QUESTIONS = [
  "Quali sono gli obblighi principali della CSRD dopo l'Omnibus I?",
  "Un chatbot sul sito aziendale deve dichiarare di essere un'IA?",
  'Quali incidenti vanno notificati entro 24 ore secondo la NIS2?',
  'DORA e NIS2: quale si applica a una banca?',
]

const LANGUAGE_NAMES: Record<string, string> = { en: 'English', it: 'italiano', de: 'Deutsch', fr: 'français', es: 'español' }

export function getMockQAResponse(question: string, language: string = 'it'): DemoQAResponse {
  const q = question.toLowerCase()

  // Article-specific detection (check first - most specific)
  let response: DemoQAResponse

  // Extract article number from various patterns: "Art. 17", "Art.17", "Art 17", "Articolo 17", "Article 17", standalone "17"
  const artNumMatch = q.match(/(?:art(?:\.?|icol[eo]|icle)\s*)(\d+)/i) || q.match(/\b(\d{1,3})\b/)
  const artNum = artNumMatch ? parseInt(artNumMatch[1]) : 0
  const hasGdpr = q.includes('gdpr') || q.includes('protezione dati') || q.includes('protezione dei dati') || q.includes('data protection') || q.includes('privacy')
  const hasAiAct = q.includes('ai act') || q.includes('intelligenza artificiale') || q.includes('artificial intelligence') || /\bun.ia\b/.test(q) || /\bsistem[ai] di ia\b/.test(q)
  const hasDora = q.includes('dora')

  if ((artNum === 17 && hasGdpr) || q.includes('diritto alla cancellazione') || q.includes("diritto all'oblio") || q.includes('right to erasure') || q.includes('right to be forgotten'))
    response = QA_RESPONSES.gdpr_art17
  else if (artNum === 13 && hasGdpr)
    response = QA_RESPONSES.gdpr_art13
  else if (artNum === 9 && hasGdpr)
    response = QA_RESPONSES.gdpr_art9
  else if (artNum === 9 && hasAiAct)
    response = QA_RESPONSES.ai_act_art9
  else if (artNum === 30 && hasDora)
    response = QA_RESPONSES.dora_art30
  else if (q.includes('dati sensibili') || q.includes('categorie particolari') || q.includes('special categories') || q.includes('dati biometrici') || q.includes('dati genetici'))
    response = QA_RESPONSES.gdpr_art9

  // Transparency for systems that talk to people (the landing's own example)
  else if (q.includes('chatbot') || q.includes('assistente virtuale') || q.includes('deepfake') || (hasAiAct && (artNum === 50 || q.includes('trasparenza') || q.includes('transparency') || q.includes('dichiarare'))))
    response = QA_RESPONSES.ai_act_art50

  // Cross-framework detection (check next - more specific than single framework)
  else if ((q.includes('ai act') || q.includes('artificial intelligence')) && (q.includes('gdpr') || q.includes('data protection') || q.includes('credit scor')))
    response = QA_RESPONSES.cross_ai_gdpr
  else if ((q.includes('dora') || q.includes('digital operational') || q.includes('resilienza')) && (q.includes('nis2') || q.includes('nis 2') || q.includes('sicurezza informatica')))
    response = QA_RESPONSES.cross_dora_nis2
  else if ((q.includes('csrd') || q.includes('scope 3') || q.includes('sustainability reporting') || q.includes('rendicontazione')) && (q.includes('csddd') || q.includes('due diligence') || q.includes('supply chain') || q.includes('catena')))
    response = QA_RESPONSES.cross_csrd_csddd
  else if ((q.includes('csddd') || q.includes('catena del valore') || q.includes('supply chain')) && (q.includes('csrd') || q.includes('scope 3') || q.includes('esrs')))
    response = QA_RESPONSES.cross_csrd_csddd

  // DPO-specific (before generic GDPR)
  else if (q.includes('dpo') || q.includes('data protection officer') || q.includes('responsabile protezione') || q.includes('responsabile della protezione') || ((q.includes('gdpr') || q.includes('protezione dati')) && (q.includes('art. 37') || q.includes('art.37') || q.includes('art 37') || q.includes('art. 38') || q.includes('art. 39'))))
    response = QA_RESPONSES.gdpr_dpo

  // Single framework
  else if (hasAiAct || q.includes('alto rischio') || q.includes('high-risk'))
    response = QA_RESPONSES.ai_act
  else if (hasGdpr || q.includes('dati personali'))
    response = QA_RESPONSES.gdpr
  else if (q.includes('dora') || q.includes('digital operational') || q.includes('resilience') || q.includes('resilienza'))
    response = QA_RESPONSES.dora
  else if (q.includes('nis2') || q.includes('nis 2') || q.includes('incident reporting') || q.includes('cybersecurity') || q.includes('sicurezza informatica') || q.includes('meldepflicht'))
    response = QA_RESPONSES.nis2
  else if (q.includes('taxonomy') || q.includes('tassonomia') || q.includes('attività sostenibil') || q.includes('ecosostenibil'))
    response = QA_RESPONSES.taxonomy
  else if (q.includes('csddd') || q.includes('due diligence') || q.includes('dovere di diligenza') || q.includes('catena del valore') || q.includes('supply chain'))
    response = QA_RESPONSES.csddd
  else if (q.includes('csrd') || q.includes('sustainability reporting') || q.includes('rendicontazione') || q.includes('omnibus'))
    response = QA_RESPONSES.csrd
  else {
    // Honest "not covered": the demo abstains instead of inventing an answer.
    response = {
      answer:
        'La demo copre alcuni scenari di esempio e questa domanda non rientra tra quelli. Con il backend attivo NormaAI cerca nel corpus di EUR-Lex e Normattiva e risponde con le citazioni, oppure si astiene quando il testo non basta.',
      citations: [],
      confidence_score: 0.0,
      requires_expert_review: false,
      related_frameworks: [],
      caveats: [],
      abstention_reason: 'demo_not_covered',
      suggested_questions: DEMO_SUGGESTED_QUESTIONS,
    }
  }

  // Language-aware: add caveat when not Italian (mock responses are in IT)
  if (language && language !== 'it') {
    const langName = LANGUAGE_NAMES[language] || language.toUpperCase()
    response = {
      ...response,
      caveats: [
        ...(response.caveats || []),
        `Lingua selezionata: ${langName}. In modalità demo le risposte sono in italiano. In produzione, NormaAI risponde nella lingua richiesta (${langName}).`,
      ],
    }
  }

  return { ...response, corpus_as_of: DEMO_CORPUS_AS_OF }
}

// ─── Gap Analysis Mocks - framework-specific ────────────────

const GAP_DATA: Record<string, { requirements: GapAnalysisResponse['requirements']; score: number; recommendations: string[] }> = {
  CSRD: {
    score: 43,
    requirements: [
      { requirement_id: 'CSRD-001', description: 'Double materiality assessment', article_reference: 'Art. 19a(2)', status: 'NON_COMPLIANT' as ComplianceStatus, evidence: '', gap_description: 'No double materiality assessment conducted', remediation_effort: '4-6 weeks', priority: 'P1' as const, notes: '' },
      { requirement_id: 'CSRD-002', description: 'Stakeholder engagement process', article_reference: 'Art. 19a(3)', status: 'PARTIALLY_COMPLIANT' as ComplianceStatus, evidence: 'Annual report 2024', gap_description: 'Not formalized per ESRS', remediation_effort: '2-3 weeks', priority: 'P2' as const, notes: '' },
      { requirement_id: 'CSRD-003', description: 'GHG emissions disclosure (Scope 1-3)', article_reference: 'ESRS E1', status: 'PARTIALLY_COMPLIANT' as ComplianceStatus, evidence: 'Scope 1-2 report', gap_description: 'Scope 3 missing', remediation_effort: '6-8 weeks', priority: 'P1' as const, notes: '' },
      { requirement_id: 'CSRD-004', description: 'Governance of sustainability matters', article_reference: 'ESRS 2 GOV-1', status: 'COMPLIANT' as ComplianceStatus, evidence: 'Board ESG committee', gap_description: '', remediation_effort: '', priority: 'P4' as const, notes: '' },
      { requirement_id: 'CSRD-005', description: 'Business model and value chain', article_reference: 'ESRS 2 SBM-1', status: 'NON_COMPLIANT' as ComplianceStatus, evidence: '', gap_description: 'No ESRS-aligned value chain mapping', remediation_effort: '3-4 weeks', priority: 'P2' as const, notes: '' },
      { requirement_id: 'CSRD-006', description: 'Biodiversity and ecosystems', article_reference: 'ESRS E4', status: 'NOT_APPLICABLE' as ComplianceStatus, evidence: 'Sector analysis', gap_description: '', remediation_effort: '', priority: 'P4' as const, notes: '' },
      { requirement_id: 'CSRD-007', description: 'Workers in the value chain', article_reference: 'ESRS S2', status: 'IN_EVOLUTION' as ComplianceStatus, evidence: 'Code of conduct draft', gap_description: 'Due diligence in development', remediation_effort: '8-10 weeks', priority: 'P1' as const, notes: '' },
    ],
    recommendations: [
      'Prioritize double materiality assessment - required before all ESRS disclosures',
      'Engage GHG consultant for Scope 3 emissions mapping',
      'Formalize stakeholder engagement per ESRS 2 SBM-2',
      'Develop ESRS-aligned value chain mapping',
      'Accelerate supply chain due diligence for ESRS S2',
    ],
  },
  AI_ACT: {
    score: 38,
    requirements: [
      { requirement_id: 'AI-001', description: 'AI system inventory and classification', article_reference: 'Art. 6, Annex III', status: 'NON_COMPLIANT' as ComplianceStatus, evidence: '', gap_description: 'No inventory of AI systems by risk category', remediation_effort: '3-4 weeks', priority: 'P1' as const, notes: '' },
      { requirement_id: 'AI-002', description: 'Risk management system for high-risk AI', article_reference: 'Art. 9', status: 'NON_COMPLIANT' as ComplianceStatus, evidence: '', gap_description: 'No AI-specific risk management framework', remediation_effort: '6-8 weeks', priority: 'P1' as const, notes: '' },
      { requirement_id: 'AI-003', description: 'Data governance for training datasets', article_reference: 'Art. 10', status: 'PARTIALLY_COMPLIANT' as ComplianceStatus, evidence: 'Data quality policy exists', gap_description: 'Not AI Act-specific, missing bias assessment', remediation_effort: '4-6 weeks', priority: 'P1' as const, notes: '' },
      { requirement_id: 'AI-004', description: 'Transparency and user notification', article_reference: 'Art. 13, Art. 50', status: 'PARTIALLY_COMPLIANT' as ComplianceStatus, evidence: 'Privacy notices mention AI', gap_description: 'Missing AI Act-specific disclosures', remediation_effort: '2-3 weeks', priority: 'P2' as const, notes: '' },
      { requirement_id: 'AI-005', description: 'Human oversight mechanisms', article_reference: 'Art. 14', status: 'COMPLIANT' as ComplianceStatus, evidence: 'Human-in-the-loop process', gap_description: '', remediation_effort: '', priority: 'P3' as const, notes: '' },
      { requirement_id: 'AI-006', description: 'Fundamental rights impact assessment', article_reference: 'Art. 27', status: 'NON_COMPLIANT' as ComplianceStatus, evidence: '', gap_description: 'No FRIA performed for high-risk AI deployments', remediation_effort: '4-5 weeks', priority: 'P1' as const, notes: '' },
      { requirement_id: 'AI-007', description: 'Conformity assessment procedure', article_reference: 'Art. 43', status: 'NOT_APPLICABLE' as ComplianceStatus, evidence: '', gap_description: '', remediation_effort: '', priority: 'P4' as const, notes: 'Applicable only if developing/placing on market' },
    ],
    recommendations: [
      'Create comprehensive AI system inventory categorized by risk level',
      'Implement AI-specific risk management system per Art. 9',
      'Perform fundamental rights impact assessment for all high-risk AI',
      'Enhance data governance with bias detection and mitigation',
      'Update transparency disclosures for AI Act compliance',
    ],
  },
  DORA: {
    score: 55,
    requirements: [
      { requirement_id: 'DORA-001', description: 'ICT risk management framework', article_reference: 'Art. 6-16', status: 'PARTIALLY_COMPLIANT' as ComplianceStatus, evidence: 'IT risk policy 2024', gap_description: 'Exists but not DORA-aligned', remediation_effort: '4-6 weeks', priority: 'P1' as const, notes: '' },
      { requirement_id: 'DORA-002', description: 'ICT incident classification & reporting', article_reference: 'Art. 17-23', status: 'PARTIALLY_COMPLIANT' as ComplianceStatus, evidence: 'Incident process exists', gap_description: 'Missing 4-hour initial notification', remediation_effort: '3-4 weeks', priority: 'P1' as const, notes: '' },
      { requirement_id: 'DORA-003', description: 'Digital resilience testing programme', article_reference: 'Art. 24-27', status: 'COMPLIANT' as ComplianceStatus, evidence: 'Annual pentest reports', gap_description: '', remediation_effort: '', priority: 'P3' as const, notes: 'TLPT may be required every 3 years' },
      { requirement_id: 'DORA-004', description: 'ICT third-party risk management', article_reference: 'Art. 28-44', status: 'NON_COMPLIANT' as ComplianceStatus, evidence: '', gap_description: 'No register of ICT service providers, missing contractual clauses', remediation_effort: '8-10 weeks', priority: 'P1' as const, notes: '' },
      { requirement_id: 'DORA-005', description: 'Information sharing arrangements', article_reference: 'Art. 45', status: 'NOT_APPLICABLE' as ComplianceStatus, evidence: '', gap_description: '', remediation_effort: '', priority: 'P4' as const, notes: 'Voluntary provision' },
      { requirement_id: 'DORA-006', description: 'ICT business continuity policy', article_reference: 'Art. 11', status: 'COMPLIANT' as ComplianceStatus, evidence: 'BCP and DRP documented', gap_description: '', remediation_effort: '', priority: 'P3' as const, notes: '' },
    ],
    recommendations: [
      'Align ICT risk management framework to DORA Art. 6 requirements',
      'Implement 4-hour incident notification process per Art. 19',
      'Create ICT third-party service provider register with risk assessment',
      'Add DORA-specific contractual clauses for all ICT providers',
      'Schedule TLPT assessment if entity qualifies as significant',
    ],
  },
  NIS2: {
    score: 47,
    requirements: [
      { requirement_id: 'NIS2-001', description: 'Cybersecurity risk-management measures', article_reference: 'Art. 21(2)', status: 'PARTIALLY_COMPLIANT' as ComplianceStatus, evidence: 'ISO 27001 cert', gap_description: 'Missing supply chain security measures', remediation_effort: '4-6 weeks', priority: 'P1' as const, notes: '' },
      { requirement_id: 'NIS2-002', description: 'Incident handling and reporting', article_reference: 'Art. 23', status: 'NON_COMPLIANT' as ComplianceStatus, evidence: '', gap_description: 'No 24h early warning process established', remediation_effort: '3-4 weeks', priority: 'P1' as const, notes: '' },
      { requirement_id: 'NIS2-003', description: 'Business continuity and crisis management', article_reference: 'Art. 21(2)(c)', status: 'COMPLIANT' as ComplianceStatus, evidence: 'BCP & DRP documents', gap_description: '', remediation_effort: '', priority: 'P3' as const, notes: '' },
      { requirement_id: 'NIS2-004', description: 'Supply chain security', article_reference: 'Art. 21(2)(d)', status: 'NON_COMPLIANT' as ComplianceStatus, evidence: '', gap_description: 'No supplier cybersecurity assessment program', remediation_effort: '6-8 weeks', priority: 'P1' as const, notes: '' },
      { requirement_id: 'NIS2-005', description: 'Management body oversight', article_reference: 'Art. 20', status: 'PARTIALLY_COMPLIANT' as ComplianceStatus, evidence: 'Board receives IT reports', gap_description: 'No formal cybersecurity training for management', remediation_effort: '2-3 weeks', priority: 'P2' as const, notes: '' },
      { requirement_id: 'NIS2-006', description: 'Vulnerability disclosure coordination', article_reference: 'Art. 21(2)(e)', status: 'IN_EVOLUTION' as ComplianceStatus, evidence: 'Vulnerability policy draft', gap_description: 'Coordinated disclosure process in development', remediation_effort: '3-4 weeks', priority: 'P2' as const, notes: '' },
    ],
    recommendations: [
      'Establish 24-hour early warning incident reporting process',
      'Implement supply chain cybersecurity assessment program',
      'Provide formal cybersecurity training for management body',
      'Finalize coordinated vulnerability disclosure policy',
      'Extend ISO 27001 controls to cover NIS2-specific requirements',
    ],
  },
  TAXONOMY: {
    score: 31,
    requirements: [
      { requirement_id: 'TAX-001', description: 'Turnover alignment disclosure', article_reference: 'Art. 8(2)(a)', status: 'NON_COMPLIANT' as ComplianceStatus, evidence: '', gap_description: 'No taxonomy-aligned turnover analysis performed', remediation_effort: '6-8 weeks', priority: 'P1' as const, notes: '' },
      { requirement_id: 'TAX-002', description: 'CapEx alignment disclosure', article_reference: 'Art. 8(2)(b)', status: 'NON_COMPLIANT' as ComplianceStatus, evidence: '', gap_description: 'No CapEx taxonomy analysis', remediation_effort: '4-6 weeks', priority: 'P1' as const, notes: '' },
      { requirement_id: 'TAX-003', description: 'Substantial contribution criteria', article_reference: 'Art. 3(a)', status: 'PARTIALLY_COMPLIANT' as ComplianceStatus, evidence: 'Some activities screened', gap_description: 'Not all eligible activities assessed', remediation_effort: '4-5 weeks', priority: 'P2' as const, notes: '' },
      { requirement_id: 'TAX-004', description: 'DNSH assessment', article_reference: 'Art. 3(b)', status: 'NON_COMPLIANT' as ComplianceStatus, evidence: '', gap_description: 'No Do No Significant Harm analysis', remediation_effort: '5-7 weeks', priority: 'P1' as const, notes: '' },
      { requirement_id: 'TAX-005', description: 'Minimum safeguards compliance', article_reference: 'Art. 18', status: 'COMPLIANT' as ComplianceStatus, evidence: 'OECD guidelines, UN principles', gap_description: '', remediation_effort: '', priority: 'P3' as const, notes: '' },
    ],
    recommendations: [
      'Perform comprehensive taxonomy eligibility screening for all activities',
      'Conduct DNSH assessment for each substantial contribution claim',
      'Calculate and disclose turnover, CapEx and OpEx alignment ratios',
      'Implement data collection process for ongoing taxonomy reporting',
      'Align with latest delegated acts and technical screening criteria',
    ],
  },
  GDPR: {
    score: 72,
    requirements: [
      { requirement_id: 'GDPR-001', description: 'Record of processing activities (RoPA)', article_reference: 'Art. 30', status: 'COMPLIANT' as ComplianceStatus, evidence: 'RoPA maintained in OneTrust', gap_description: '', remediation_effort: '', priority: 'P3' as const, notes: '' },
      { requirement_id: 'GDPR-002', description: 'Data Protection Impact Assessment', article_reference: 'Art. 35', status: 'PARTIALLY_COMPLIANT' as ComplianceStatus, evidence: 'DPIA for main systems', gap_description: 'Missing DPIA for 3 new processing activities', remediation_effort: '3-4 weeks', priority: 'P2' as const, notes: '' },
      { requirement_id: 'GDPR-003', description: 'Data subject rights mechanism', article_reference: 'Art. 15-22', status: 'COMPLIANT' as ComplianceStatus, evidence: 'DSR portal operational', gap_description: '', remediation_effort: '', priority: 'P3' as const, notes: '' },
      { requirement_id: 'GDPR-004', description: 'Data breach notification', article_reference: 'Art. 33-34', status: 'COMPLIANT' as ComplianceStatus, evidence: 'Breach process documented', gap_description: '', remediation_effort: '', priority: 'P3' as const, notes: '' },
      { requirement_id: 'GDPR-005', description: 'International data transfers', article_reference: 'Art. 44-49', status: 'PARTIALLY_COMPLIANT' as ComplianceStatus, evidence: 'SCCs in place', gap_description: 'Missing TIA for 2 transfers', remediation_effort: '2-3 weeks', priority: 'P2' as const, notes: '' },
      { requirement_id: 'GDPR-006', description: 'DPO appointment and independence', article_reference: 'Art. 37-39', status: 'COMPLIANT' as ComplianceStatus, evidence: 'DPO appointed', gap_description: '', remediation_effort: '', priority: 'P4' as const, notes: '' },
    ],
    recommendations: [
      'Complete DPIA for new processing activities',
      'Finalize Transfer Impact Assessments for US/UK data flows',
      'Update SCCs to latest Commission template',
      'Review and refresh consent mechanisms for marketing',
      'Schedule annual RoPA review with business units',
    ],
  },
  CSDDD: {
    score: 28,
    requirements: [
      { requirement_id: 'CSDDD-001', description: 'Human rights due diligence process', article_reference: 'Art. 7-8', status: 'NON_COMPLIANT' as ComplianceStatus, evidence: '', gap_description: 'No systematic human rights due diligence', remediation_effort: '8-12 weeks', priority: 'P1' as const, notes: '' },
      { requirement_id: 'CSDDD-002', description: 'Environmental due diligence', article_reference: 'Art. 7-8', status: 'PARTIALLY_COMPLIANT' as ComplianceStatus, evidence: 'EMS exists', gap_description: 'Not extended to full value chain', remediation_effort: '6-8 weeks', priority: 'P1' as const, notes: '' },
      { requirement_id: 'CSDDD-003', description: 'Climate transition plan', article_reference: 'Art. 22', status: 'NON_COMPLIANT' as ComplianceStatus, evidence: '', gap_description: 'No Paris-aligned transition plan', remediation_effort: '8-10 weeks', priority: 'P1' as const, notes: '' },
      { requirement_id: 'CSDDD-004', description: 'Complaints mechanism', article_reference: 'Art. 14', status: 'NON_COMPLIANT' as ComplianceStatus, evidence: '', gap_description: 'No grievance mechanism for affected stakeholders', remediation_effort: '4-6 weeks', priority: 'P2' as const, notes: '' },
      { requirement_id: 'CSDDD-005', description: 'Stakeholder engagement in DD', article_reference: 'Art. 13', status: 'IN_EVOLUTION' as ComplianceStatus, evidence: 'Initial mapping done', gap_description: 'Engagement process not formalized', remediation_effort: '3-4 weeks', priority: 'P2' as const, notes: '' },
    ],
    recommendations: [
      'Develop comprehensive human rights due diligence process per Art. 7',
      'Extend environmental due diligence to full upstream and downstream chain',
      'Adopt Paris-aligned climate transition plan per Art. 22',
      'Establish accessible complaints mechanism for affected stakeholders',
      'Formalize stakeholder engagement in due diligence process',
    ],
  },
}

export function getMockGapAnalysis(framework: string): GapAnalysisResponse {
  const data = GAP_DATA[framework] || GAP_DATA.CSRD

  const statusCounts = data.requirements.reduce(
    (acc, r) => {
      if (r.status === 'COMPLIANT') acc.compliant++
      else if (r.status === 'PARTIALLY_COMPLIANT') acc.partially_compliant++
      else if (r.status === 'NON_COMPLIANT') acc.non_compliant++
      else if (r.status === 'NOT_APPLICABLE') acc.not_applicable++
      else if (r.status === 'IN_EVOLUTION') acc.in_evolution++
      return acc
    },
    { compliant: 0, partially_compliant: 0, non_compliant: 0, not_applicable: 0, in_evolution: 0 },
  )

  return {
    framework,
    overall_score: data.score,
    status_summary: statusCounts,
    requirements: data.requirements,
    top_recommendations: data.recommendations,
    confidence_score: 0.85 + Math.random() * 0.1,
    requires_expert_review: false,
  }
}

// ─── Monitor Mock - input-aware ─────────────────────────────

const MONITOR_SCENARIOS: Record<string, MonitorResponse> = {
  csrd: {
    applicability: 'YES',
    applicability_reason: 'The company exceeds the proposed 1,000 employee threshold under the Omnibus I revision (Art. 19a CSRD). The change directly affects reporting obligations.',
    urgency: 'HIGH',
    impact_summary: 'La proposta Omnibus I riduce significativamente il numero di imprese soggette al CSRD innalzando la soglia da 250 a 1.000 dipendenti. Per la vostra azienda con 2.500 dipendenti, l\'obbligo rimane, ma i tempi e i requisiti semplificati per le PMI cambiano il contesto competitivo.',
    required_actions: [
      'Verificare le nuove soglie e confermare l\'applicabilità (1 giorno)',
      'Aggiornare la roadmap di compliance con le nuove scadenze (2-3 giorni)',
      'Rivedere l\'analisi di materialità alla luce dei criteri semplificati (2-4 settimane)',
      'Comunicare al board le modifiche e il potenziale impatto (1 giorno)',
      'Monitorare l\'iter legislativo del pacchetto Omnibus (ongoing)',
    ],
    deadline: '2026-01-01',
    deadline_is_confirmed: false,
    cross_framework_impacts: [
      'CSDDD: Soglia innalzata a 1.000 dipendenti nella proposta Omnibus I',
      'EU Taxonomy: Allineamento con le nuove soglie CSRD per la disclosure tassonomica',
    ],
    confidence_score: 0.88,
    requires_expert_review: false,
    citations: ['CSRD, Art. 19a(1)', 'Omnibus I Proposal COM(2025)80', 'CSDDD, Art. 2'],
  },
  nis2: {
    applicability: 'YES',
    applicability_reason: 'Il settore manifatturiero con 2.500 dipendenti rientra tra le entità importanti ai sensi dell\'Annex II della NIS2. L\'estensione del campo di applicazione include esplicitamente il manufacturing.',
    urgency: 'HIGH',
    impact_summary: 'L\'estensione della NIS2 al settore manifatturiero impone nuovi obblighi di cybersecurity: gestione del rischio, incident reporting in 3 fasi, governance della sicurezza a livello di management body, e sicurezza della supply chain digitale.',
    required_actions: [
      'Verificare la classificazione come entità essenziale o importante (1 settimana)',
      'Mappare i gap rispetto ai requisiti Art. 21(2) con l\'attuale ISO 27001 (2-3 settimane)',
      'Implementare il processo di incident reporting 24h/72h/1 mese (3-4 settimane)',
      'Organizzare formazione cybersecurity per il management body Art. 20 (2 settimane)',
      'Avviare assessment cybersecurity della supply chain Art. 21(2)(d) (6-8 settimane)',
    ],
    deadline: '2026-10-17',
    deadline_is_confirmed: true,
    cross_framework_impacts: [
      'DORA: Se l\'azienda opera anche nel settore finanziario, DORA prevale come lex specialis (Art. 4 NIS2)',
      'GDPR: Data breach notification (72h GDPR) si sovrappone a incident reporting NIS2',
    ],
    confidence_score: 0.91,
    requires_expert_review: false,
    citations: ['NIS2, Art. 2, Annex II', 'NIS2, Art. 21(2)', 'NIS2, Art. 23'],
  },
  dora: {
    applicability: 'CONDITIONAL',
    applicability_reason: 'DORA si applica alle entità finanziarie. Se l\'azienda opera nel settore finanziario o fornisce servizi ICT a entità finanziarie, è soggetta a DORA.',
    urgency: 'CRITICAL',
    impact_summary: 'L\'aggiornamento dei Technical Standards DORA da parte dell\'ESA Joint Committee introduce nuovi requisiti per il testing di resilienza digitale e la gestione del rischio ICT di terze parti. Le entità finanziarie devono aggiornare i contratti con i fornitori ICT entro 6 mesi.',
    required_actions: [
      'Verificare se l\'azienda è soggetta a DORA come entità finanziaria o fornitore ICT (1 settimana)',
      'Rivedere tutti i contratti ICT alla luce dei nuovi Technical Standards (4-6 settimane)',
      'Aggiornare il framework di ICT risk management Art. 6-16 (3-4 settimane)',
      'Pianificare TLPT se l\'entità è classificata come significativa (8-12 settimane)',
      'Integrare i requisiti di information sharing Art. 45 (2-3 settimane)',
    ],
    deadline: '2025-01-17',
    deadline_is_confirmed: true,
    cross_framework_impacts: [
      'NIS2: DORA prevale come lex specialis per le entità finanziarie (NIS2 Art. 4)',
      'GDPR: ICT incident con data breach richiede doppia notifica (DORA + GDPR Art. 33)',
    ],
    confidence_score: 0.86,
    requires_expert_review: true,
    citations: ['DORA, Art. 6', 'DORA, Art. 28', 'ESA Joint Committee RTS/ITS 2025'],
  },
  ai_act: {
    applicability: 'YES',
    applicability_reason: 'Se l\'azienda sviluppa o utilizza sistemi AI, l\'AI Act impone obblighi proporzionati al livello di rischio. L\'aggiornamento delle linee guida dell\'AI Office chiarisce i criteri di classificazione.',
    urgency: 'MEDIUM',
    impact_summary: 'Le nuove linee guida dell\'AI Office definiscono con maggiore precisione i criteri per classificare i sistemi AI come alto rischio. Per le aziende manifatturiere, i sistemi AI di controllo qualità e manutenzione predittiva potrebbero rientrare nell\'Annex III se integrati in componenti di sicurezza.',
    required_actions: [
      'Censire tutti i sistemi AI in uso nell\'organizzazione (2-3 settimane)',
      'Classificare ogni sistema per livello di rischio secondo le nuove linee guida (1-2 settimane)',
      'Per sistemi ad alto rischio: avviare conformity assessment Art. 43 (8-12 settimane)',
      'Implementare requisiti di trasparenza Art. 50 per sistemi AI customer-facing (3-4 settimane)',
      'Formare il team AI sugli obblighi del provider/deployer (1 settimana)',
    ],
    deadline: '2026-08-02',
    deadline_is_confirmed: true,
    cross_framework_impacts: [
      'GDPR: DPIA obbligatoria per sistemi AI che trattano dati personali (GDPR Art. 35)',
      'Product Safety: AI in componenti di sicurezza soggetta anche al Product Liability Directive',
    ],
    confidence_score: 0.84,
    requires_expert_review: true,
    citations: ['AI Act, Art. 6', 'AI Act, Annex III', 'AI Office Guidelines 2025'],
  },
}

const MONITOR_EXTRA_SCENARIOS: Record<string, MonitorResponse> = {
  csddd: {
    applicability: 'YES',
    applicability_reason: 'La CSDDD (Corporate Sustainability Due Diligence Directive) si applica alle imprese con oltre 1.000 dipendenti e €450M di fatturato netto. Con 2.500 dipendenti e €200M, l\'azienda potrebbe rientrare nel campo di applicazione a partire dalla seconda fase (2028).',
    urgency: 'MEDIUM',
    impact_summary: 'La CSDDD impone obblighi di due diligence sulla catena del valore per identificare, prevenire e mitigare impatti negativi sui diritti umani e sull\'ambiente. Le aziende devono mappare l\'intera supply chain, implementare un piano di transizione climatica e integrare la due diligence nella governance aziendale.',
    required_actions: [
      'Mappare la catena del valore e identificare le operazioni a rischio (4-8 settimane)',
      'Implementare un meccanismo di reclamo accessibile agli stakeholder (3-4 settimane)',
      'Adottare un piano di transizione climatica allineato a 1.5°C (8-12 settimane)',
      'Integrare la due diligence nella politica aziendale e governance (2-4 settimane)',
      'Monitorare l\'iter legislativo per le soglie definitive post-Omnibus (ongoing)',
    ],
    deadline: '2027-07-26',
    deadline_is_confirmed: false,
    cross_framework_impacts: [
      'CSRD: Gli obblighi di reporting CSRD richiedono disclosure sulla due diligence CSDDD',
      'EU Taxonomy: L\'allineamento tassonomico richiede considerazioni di "do no significant harm" coerenti con CSDDD',
    ],
    confidence_score: 0.82,
    requires_expert_review: true,
    citations: ['CSDDD, Art. 5-11', 'CSDDD, Art. 15 (piano climatico)', 'Omnibus I Proposal COM(2025)80'],
  },
  taxonomy: {
    applicability: 'YES',
    applicability_reason: 'Le imprese soggette a CSRD devono dichiarare la quota di attività economiche allineate alla EU Taxonomy. I nuovi delegated acts estendono i criteri tecnici di screening agli obiettivi ambientali 3-6.',
    urgency: 'HIGH',
    impact_summary: 'L\'aggiornamento dei delegated acts della EU Taxonomy introduce nuovi criteri tecnici di screening per attività economiche legate a uso sostenibile dell\'acqua, economia circolare, prevenzione dell\'inquinamento e biodiversità. Le aziende manifatturiere devono rivalutare l\'allineamento tassonomico delle proprie attività.',
    required_actions: [
      'Rivalutare le attività economiche alla luce dei nuovi criteri per obiettivi 3-6 (3-4 settimane)',
      'Aggiornare il calcolo di CapEx/OpEx/Turnover allineati alla Taxonomy (2-3 settimane)',
      'Verificare il rispetto dei criteri DNSH (Do No Significant Harm) aggiornati (2 settimane)',
      'Integrare i nuovi criteri nel reporting CSRD/ESRS (1-2 settimane)',
      'Formare il team finance sui nuovi requisiti di disclosure (1 settimana)',
    ],
    deadline: '2026-01-01',
    deadline_is_confirmed: true,
    cross_framework_impacts: [
      'CSRD: La disclosure tassonomica è parte integrante del sustainability statement ESRS',
      'SFDR: I fondi Article 8/9 devono dichiarare l\'allineamento tassonomico dei portafogli',
    ],
    confidence_score: 0.87,
    requires_expert_review: false,
    citations: ['EU Taxonomy Regulation Art. 8', 'Delegated Regulation 2023/2486', 'ESRS E1-E5'],
  },
  gdpr: {
    applicability: 'YES',
    applicability_reason: 'Il GDPR si applica a tutte le organizzazioni che trattano dati personali di interessati nell\'UE. Le nuove linee guida EDPB chiariscono obblighi per il trasferimento dati e l\'uso di AI nel trattamento.',
    urgency: 'MEDIUM',
    impact_summary: 'Le nuove linee guida EDPB sul trasferimento internazionale di dati e sull\'uso di sistemi AI nel trattamento automatizzato richiedono una revisione delle valutazioni di impatto (DPIA) e delle clausole contrattuali standard (SCCs). Particolare attenzione per le aziende che utilizzano fornitori SaaS extra-UE.',
    required_actions: [
      'Aggiornare il registro dei trattamenti con i nuovi flussi di dati identificati (1-2 settimane)',
      'Revisionare le DPIA per trattamenti che coinvolgono AI/decisioni automatizzate (3-4 settimane)',
      'Aggiornare le SCCs al template Commission più recente per trasferimenti extra-UE (2-3 settimane)',
      'Verificare la conformità dei sub-responsabili e fornitori cloud (2-4 settimane)',
      'Implementare o aggiornare la procedura di data breach notification 72h (1 settimana)',
    ],
    deadline: '',
    deadline_is_confirmed: false,
    cross_framework_impacts: [
      'AI Act: DPIA obbligatoria per sistemi AI ad alto rischio che trattano dati personali (GDPR Art. 35 + AI Act Art. 9)',
      'NIS2: Data breach notification si sovrappone tra GDPR (72h) e NIS2 (24h early warning)',
    ],
    confidence_score: 0.89,
    requires_expert_review: false,
    citations: ['GDPR Art. 33-34', 'GDPR Art. 35 (DPIA)', 'EDPB Guidelines 2025'],
  },
}

export function getMockMonitorResponse(changeText?: string): MonitorResponse {
  if (!changeText) return MONITOR_SCENARIOS.csrd

  const t = changeText.toLowerCase()

  if (t.includes('nis2') || t.includes('cybersecurity') || t.includes('manufacturing sector') || t.includes('sicurezza informatica'))
    return MONITOR_SCENARIOS.nis2
  if (t.includes('dora') || t.includes('digital operational') || t.includes('resilienza operativa') || t.includes('financial'))
    return MONITOR_SCENARIOS.dora
  if (t.includes('ai act') || t.includes('artificial intelligence') || t.includes('intelligenza artificiale') || t.includes('alto rischio'))
    return MONITOR_SCENARIOS.ai_act
  if (t.includes('csddd') || t.includes('due diligence') || t.includes('supply chain') || t.includes('catena di fornitura') || t.includes('catena del valore'))
    return MONITOR_EXTRA_SCENARIOS.csddd
  if (t.includes('taxonomy') || t.includes('tassonomia') || t.includes('green finance') || t.includes('screening criteria') || t.includes('delegated act'))
    return MONITOR_EXTRA_SCENARIOS.taxonomy
  if (t.includes('gdpr') || t.includes('data protection') || t.includes('protezione dati') || t.includes('privacy') || t.includes('dati personali'))
    return MONITOR_EXTRA_SCENARIOS.gdpr
  if (t.includes('csrd') || t.includes('omnibus') || t.includes('sustainability reporting') || t.includes('soglia'))
    return MONITOR_SCENARIOS.csrd

  // Generic response for unknown input
  return {
    applicability: 'CONDITIONAL',
    applicability_reason: 'La modifica normativa descritta potrebbe essere applicabile all\'azienda. È necessaria un\'analisi più approfondita per confermare l\'impatto specifico.',
    urgency: 'MEDIUM',
    impact_summary: `La modifica normativa richiede una valutazione d'impatto specifica. In modalità demo, NormaAI fornisce analisi pre-configurate per le principali normative EU (CSRD, DORA, NIS2, AI Act). Con il backend attivo, l'analisi viene generata dinamicamente tramite RAG e LLM.`,
    required_actions: [
      'Identificare il framework normativo specifico coinvolto (1-2 giorni)',
      'Verificare l\'applicabilità alla vostra azienda in base a soglie e settore (1 settimana)',
      'Mappare i gap rispetto ai nuovi requisiti (2-4 settimane)',
      'Consultare il team legale per una valutazione formale (ongoing)',
    ],
    deadline: '',
    deadline_is_confirmed: false,
    cross_framework_impacts: [],
    confidence_score: 0.5,
    requires_expert_review: true,
    citations: [],
  }
}

// ─── Clients Mock ──────────────────────────────────────────

export const DEMO_CLIENTS = [
  { id: 'demo-c1', name: 'EnergiePlus GmbH', sector: 'Energy', employee_count: 5000, revenue_eur: 800_000_000, jurisdictions: ['DE', 'AT', 'PL'], applicable_frameworks: ['CSRD', 'CSDDD', 'TAXONOMY', 'NIS2'], created_at: '2026-01-12T09:30:00Z', updated_at: '2026-03-02T15:10:00Z' },
  { id: 'demo-c2', name: 'Banca Meridiana S.p.A.', sector: 'Financial Services', employee_count: 3200, revenue_eur: 1_200_000_000, jurisdictions: ['IT', 'ES'], applicable_frameworks: ['DORA', 'NIS2', 'GDPR', 'CSRD'], created_at: '2026-01-20T11:00:00Z', updated_at: '2026-02-27T10:45:00Z' },
  { id: 'demo-c3', name: 'MedTech Innovations B.V.', sector: 'Healthcare / Technology', employee_count: 1800, revenue_eur: 350_000_000, jurisdictions: ['NL', 'DE', 'FR'], applicable_frameworks: ['AI_ACT', 'GDPR', 'CSRD'], created_at: '2026-02-03T14:20:00Z', updated_at: '2026-02-20T09:05:00Z' },
  { id: 'demo-c4', name: 'LogiTrans Europe S.A.', sector: 'Transport & Logistics', employee_count: 4500, revenue_eur: 600_000_000, jurisdictions: ['FR', 'BE', 'LU', 'DE'], applicable_frameworks: ['CSRD', 'NIS2', 'CSDDD', 'TAXONOMY'], created_at: '2026-02-10T08:15:00Z', updated_at: '2026-03-01T17:30:00Z' },
]

// ─── Processors Mock ────────────────────────────────────────

export const DEMO_PROCESSORS = {
  status: 'success',
  engines: ['dots.ocr', 'docling', 'beautifulsoup'],
  dots_ocr: { available: true, mode: 'vLLM' },
  docling: { available: true },
}

// ─── Alerts Mock ────────────────────────────────────────────

export const DEMO_ALERTS = [
  { id: '1', title: 'CSRD: nuove soglie in vigore dal 18 marzo 2026 (Omnibus I)', description: 'La Direttiva (UE) 2026/470 ha portato il perimetro a oltre 1.000 dipendenti e 450 milioni di euro di ricavi netti. Verifica se l\'azienda resta in ambito e aggiorna il piano di rendicontazione.', severity: 'CRITICAL', framework: 'CSRD', is_read: false, is_dismissed: false, created_at: new Date().toISOString(), source: 'Gazzetta ufficiale dell\'Unione europea', client_id: null, regulation_id: null, actions_required: ['Verificare il perimetro con le nuove soglie', 'Aggiornare il calendario di rendicontazione'], deadline: '2026-12-31' },
  { id: '2', title: 'AI Act: obblighi di trasparenza dell\'art. 50 dal 2 agosto 2026', description: 'Chatbot, sistemi generativi, riconoscimento delle emozioni e deepfake devono rispettare gli obblighi di informazione e marcatura. Censire i sistemi in uso e assegnare i ruoli di fornitore e utilizzatore.', severity: 'HIGH', framework: 'AI_ACT', is_read: false, is_dismissed: false, created_at: new Date(Date.now() - 86400000).toISOString(), source: 'Regolamento (UE) 2024/1689, art. 113', client_id: null, regulation_id: null, actions_required: ['Censire i sistemi di IA in uso', 'Assegnare i ruoli di fornitore e utilizzatore'], deadline: '2026-08-02' },
  { id: '3', title: 'CRA: segnalazione delle vulnerabilità sfruttate dall\'11 settembre 2026', description: 'I fabbricanti di prodotti con elementi digitali devono segnalare le vulnerabilità attivamente sfruttate e gli incidenti gravi (art. 14). Predisporre il processo interno di segnalazione.', severity: 'MEDIUM', framework: 'CRA', is_read: true, is_dismissed: false, created_at: new Date(Date.now() - 172800000).toISOString(), source: 'Regolamento (UE) 2024/2847, art. 14', client_id: null, regulation_id: null, actions_required: ['Definire il processo di segnalazione'], deadline: '2026-09-11' },
  { id: '4', title: 'NIS2: verifica della classificazione come soggetto essenziale o importante', description: 'Il D.Lgs. 138/2024 recepisce la NIS2 in Italia: le imprese nei settori degli allegati, sopra le soglie di dimensione, devono registrarsi presso l\'ACN e adottare le misure dell\'art. 21.', severity: 'LOW', framework: 'NIS2', is_read: true, is_dismissed: false, created_at: new Date(Date.now() - 432000000).toISOString(), source: 'D.Lgs. 138/2024', client_id: null, regulation_id: null, actions_required: ['Verificare settore e soglie di dimensione'], deadline: null },
  { id: '5', title: 'Tassonomia: criteri di vaglio tecnico per gli obiettivi ambientali 3-6', description: 'Gli atti delegati estendono i criteri di vaglio tecnico ad altre attività economiche. Rilevante per chi deve pubblicare la quota di attività allineate alla Tassonomia.', severity: 'INFORMATIONAL', framework: 'TAXONOMY', is_read: true, is_dismissed: false, created_at: new Date(Date.now() - 604800000).toISOString(), source: 'Regolamento (UE) 2020/852, atti delegati', client_id: null, regulation_id: null, actions_required: [], deadline: null },
]

export const DEMO_ALERT_SUMMARY = {
  total: 5,
  unread: 2,
  by_severity: { CRITICAL: 1, HIGH: 1, MEDIUM: 1, LOW: 1, INFORMATIONAL: 1 } as Record<string, number>,
  by_framework: { CSRD: 1, AI_ACT: 1, CRA: 1, NIS2: 1, TAXONOMY: 1 } as Record<string, number>,
}

// ─── Delay helper ───────────────────────────────────────────

export function mockDelay(ms: number = 1500): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms))
}
