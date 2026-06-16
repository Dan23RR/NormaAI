/**
 * Mock data for demo mode — allows full frontend usage without a running backend.
 * Each framework has dedicated, realistic mock responses.
 */

import type {
  User, TokenPair, QAResponse, GapAnalysisResponse,
  MonitorResponse, SystemStats, ComplianceStatus, AuditEvent, Role, WorkflowItem,
  ClientComplianceScore, ClientComplianceHistory,
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

// ─── Knowledge Base Freshness ───────────────────────────────

export const KNOWLEDGE_BASE_META = {
  updated_at: '2026-02-28',
  chunks_count: 14823,
  frameworks_count: 7,
  frameworks: ['CSRD', 'CSDDD', 'AI Act', 'DORA', 'NIS2', 'EU Taxonomy', 'GDPR'],
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

const QA_RESPONSES: Record<string, QAResponse> = {
  csrd: {
    answer: "In base al Regolamento CSRD (Direttiva 2022/2464), le imprese con oltre 250 dipendenti, un fatturato netto superiore a 50 milioni di euro o un totale di bilancio superiore a 25 milioni di euro sono obbligate a presentare la rendicontazione di sostenibilità. Tuttavia, con il pacchetto Omnibus I proposto nel febbraio 2025, la soglia per i dipendenti potrebbe essere innalzata a 1.000, riducendo significativamente il numero di imprese coinvolte.\n\nPer la vostra azienda con 2.500 dipendenti, l'obbligo CSRD resta comunque applicabile indipendentemente dalla soglia adottata.",
    citations: [
      { framework: 'CSRD', reference: 'Art. 19a(1)', quote_snippet: 'Large undertakings shall include in the management report...' },
      { framework: 'CSRD', reference: 'Art. 2(1)', quote_snippet: 'Undertakings which exceed at least two of the three following criteria...' },
      { framework: 'CSRD', reference: 'Omnibus I Proposal', quote_snippet: 'The employee threshold is proposed to be raised to 1,000...' },
    ],
    confidence_score: 0.92,
    requires_expert_review: false,
    related_frameworks: ['CSDDD', 'EU Taxonomy'],
    caveats: ['La proposta Omnibus I è ancora in fase di negoziazione e potrebbe subire modifiche.'],
  },
  dora: {
    answer: "DORA (Digital Operational Resilience Act, Regulation 2022/2554) impone obblighi stringenti in materia di resilienza operativa digitale per tutte le entità finanziarie dell'UE. I principali obblighi includono:\n\n1. **ICT Risk Management Framework** — Implementare un framework completo per la gestione dei rischi ICT [DORA, Art. 6-16]\n2. **Incident Reporting** — Segnalazione di incidenti ICT gravi alle autorità competenti entro 4 ore dalla classificazione [DORA, Art. 17-23]\n3. **Digital Resilience Testing** — Eseguire test di resilienza annuali e TLPT ogni 3 anni per entità significative [DORA, Art. 24-27]\n4. **ICT Third-Party Risk** — Gestione del rischio dei fornitori ICT con clausole contrattuali obbligatorie [DORA, Art. 28-44]\n5. **Information Sharing** — Partecipazione a sistemi di condivisione delle informazioni sulle minacce [DORA, Art. 45]\n\nDORA è applicabile dal 17 gennaio 2025.",
    citations: [
      { framework: 'DORA', reference: 'Art. 6', quote_snippet: 'Financial entities shall have in place an ICT risk management framework...' },
      { framework: 'DORA', reference: 'Art. 19(1)', quote_snippet: 'Financial entities shall report major ICT-related incidents...' },
      { framework: 'DORA', reference: 'Art. 26(1)', quote_snippet: 'Financial entities shall carry out advanced testing by means of TLPT...' },
      { framework: 'DORA', reference: 'Art. 28(1)', quote_snippet: 'Financial entities shall manage ICT third-party risk as an integral component of ICT risk...' },
    ],
    confidence_score: 0.95,
    requires_expert_review: false,
    related_frameworks: ['NIS2'],
    caveats: [],
  },
  nis2: {
    answer: "Ai sensi della Direttiva NIS2 (2022/2555), gli obblighi di segnalazione degli incidenti prevedono un processo in tre fasi:\n\n1. **Early warning** — Entro 24 ore dal rilevamento dell'incidente significativo, notifica al CSIRT nazionale o all'autorità competente [NIS2, Art. 23(4)(a)]\n2. **Incident notification** — Entro 72 ore, fornire una valutazione iniziale con severità, impatto e indicatori di compromissione [NIS2, Art. 23(4)(b)]\n3. **Final report** — Entro 1 mese dalla notifica, report finale dettagliato con root cause analysis, misure di mitigazione e impatto transfrontaliero [NIS2, Art. 23(4)(d)]\n\nUn incidente è considerato \"significativo\" se causa gravi interruzioni operative, perdite finanziarie rilevanti o danni a persone fisiche o giuridiche [NIS2, Art. 23(3)].",
    citations: [
      { framework: 'NIS2', reference: 'Art. 23(1)', quote_snippet: 'Essential and important entities shall notify without undue delay...' },
      { framework: 'NIS2', reference: 'Art. 23(4)', quote_snippet: 'The early warning shall be submitted within 24 hours...' },
      { framework: 'NIS2', reference: 'Art. 21(2)', quote_snippet: 'Cybersecurity risk-management measures shall include policies on risk analysis...' },
    ],
    confidence_score: 0.89,
    requires_expert_review: false,
    related_frameworks: ['DORA', 'GDPR'],
    caveats: ['I termini possono variare in base alla trasposizione nazionale.'],
  },
  ai_act: {
    answer: "L'AI Act (Regolamento 2024/1689) introduce un sistema di classificazione basato sul rischio per i sistemi di intelligenza artificiale nell'UE:\n\n1. **Rischio inaccettabile** — Sistemi vietati: scoring sociale, manipolazione subliminale, sorveglianza biometrica di massa [AI Act, Art. 5]\n2. **Alto rischio** — Sistemi soggetti a requisiti stringenti: credit scoring, recruitment, infrastrutture critiche [AI Act, Art. 6, Annex III]\n3. **Rischio limitato** — Obblighi di trasparenza: chatbot, deepfake, sistemi di raccomandazione [AI Act, Art. 50]\n4. **Rischio minimo** — Nessun obbligo specifico, codici di condotta volontari\n\nI sistemi ad alto rischio devono implementare: gestione del rischio [Art. 9], governance dei dati [Art. 10], documentazione tecnica [Art. 11], trasparenza [Art. 13], supervisione umana [Art. 14] e accuratezza/robustezza [Art. 15].\n\nLe sanzioni arrivano fino a 35 milioni di euro o il 7% del fatturato globale [AI Act, Art. 99].",
    citations: [
      { framework: 'AI Act', reference: 'Art. 6', quote_snippet: 'A high-risk AI system is one that is intended to be used as a safety component...' },
      { framework: 'AI Act', reference: 'Art. 9(1)', quote_snippet: 'A risk management system shall be established and maintained...' },
      { framework: 'AI Act', reference: 'Art. 13(1)', quote_snippet: 'High-risk AI systems shall be designed to ensure transparency...' },
      { framework: 'AI Act', reference: 'Art. 99(3)', quote_snippet: 'Up to EUR 35 million or 7% of worldwide annual turnover...' },
    ],
    confidence_score: 0.91,
    requires_expert_review: false,
    related_frameworks: ['GDPR', 'DORA'],
    caveats: ['L\'AI Act è in fase di attuazione progressiva: i divieti dal febbraio 2025, i requisiti per sistemi ad alto rischio dal agosto 2026.'],
  },
  gdpr: {
    answer: "Il GDPR (Regolamento 2016/679) stabilisce i principi fondamentali per il trattamento dei dati personali nell'UE:\n\n1. **Liceità, correttezza e trasparenza** — Base giuridica obbligatoria (consenso, contratto, obbligo legale, interesse legittimo, etc.) [GDPR, Art. 6]\n2. **Limitazione della finalità** — Dati raccolti per finalità determinate, esplicite e legittime [GDPR, Art. 5(1)(b)]\n3. **Minimizzazione** — Solo dati adeguati, pertinenti e limitati al necessario [GDPR, Art. 5(1)(c)]\n4. **Diritti degli interessati** — Accesso [Art. 15], rettifica [Art. 16], cancellazione [Art. 17], portabilità [Art. 20], opposizione [Art. 21]\n5. **Data Protection Officer** — Obbligatorio per autorità pubbliche e trattamenti su larga scala [GDPR, Art. 37]\n6. **Notifica data breach** — Entro 72 ore all'autorità di controllo [GDPR, Art. 33], senza ritardo agli interessati se rischio elevato [Art. 34]\n\nLe sanzioni arrivano fino a 20 milioni di euro o il 4% del fatturato globale [GDPR, Art. 83(5)].",
    citations: [
      { framework: 'GDPR', reference: 'Art. 6(1)', quote_snippet: 'Processing shall be lawful only if and to the extent that at least one condition applies...' },
      { framework: 'GDPR', reference: 'Art. 33(1)', quote_snippet: 'The controller shall notify the supervisory authority within 72 hours...' },
      { framework: 'GDPR', reference: 'Art. 37(1)', quote_snippet: 'The controller and the processor shall designate a data protection officer...' },
    ],
    confidence_score: 0.94,
    requires_expert_review: false,
    related_frameworks: ['AI Act', 'NIS2'],
    caveats: [],
  },
  taxonomy: {
    answer: "Il Regolamento EU Taxonomy (2020/852) stabilisce un sistema di classificazione per le attività economiche sostenibili:\n\n1. **6 obiettivi ambientali** — Mitigazione cambiamento climatico, adattamento, acque, economia circolare, inquinamento, biodiversità [Taxonomy, Art. 9]\n2. **Contributo sostanziale** — L'attività deve contribuire sostanzialmente ad almeno uno dei 6 obiettivi [Taxonomy, Art. 3(a)]\n3. **Do No Significant Harm (DNSH)** — Non deve arrecare danno significativo agli altri obiettivi [Taxonomy, Art. 3(b)]\n4. **Garanzie minime di salvaguardia** — Rispetto delle linee guida OCSE e dei principi UN [Taxonomy, Art. 3(c), Art. 18]\n5. **Obblighi di disclosure** — Le imprese soggette al CSRD devono dichiarare la % di fatturato, CapEx e OpEx allineati alla Taxonomy [Taxonomy, Art. 8]\n\nI criteri tecnici di screening sono definiti negli atti delegati della Commissione.",
    citations: [
      { framework: 'EU Taxonomy', reference: 'Art. 3', quote_snippet: 'An economic activity shall qualify as environmentally sustainable where...' },
      { framework: 'EU Taxonomy', reference: 'Art. 8(1)', quote_snippet: 'Any undertaking subject to CSRD shall disclose the proportion of turnover...' },
      { framework: 'EU Taxonomy', reference: 'Art. 18', quote_snippet: 'Minimum safeguards shall be procedures implemented to ensure alignment...' },
    ],
    confidence_score: 0.87,
    requires_expert_review: false,
    related_frameworks: ['CSRD', 'CSDDD'],
    caveats: ['I criteri tecnici di screening vengono aggiornati periodicamente dalla Commissione Europea.'],
  },
  csddd: {
    answer: "La Corporate Sustainability Due Diligence Directive (CSDDD, Direttiva 2024/1760) impone obblighi di dovuta diligenza sulla catena del valore:\n\n1. **Ambito di applicazione** — Imprese UE con >1.000 dipendenti e >€450M di fatturato netto, o imprese extra-UE con >€450M di fatturato nell'UE [CSDDD, Art. 2]\n2. **Due diligence obbligatoria** — Identificare, prevenire, mitigare e rendere conto degli impatti negativi sui diritti umani e sull'ambiente [CSDDD, Art. 7-8]\n3. **Piano di transizione climatica** — Adozione di un piano compatibile con l'Accordo di Parigi (1.5°C) [CSDDD, Art. 22]\n4. **Meccanismo di reclamo** — Procedura accessibile per segnalare impatti negativi [CSDDD, Art. 14]\n5. **Responsabilità civile** — Le imprese sono responsabili per i danni causati dalla mancata due diligence [CSDDD, Art. 29]\n\nLe sanzioni includono multe fino al 5% del fatturato netto globale [CSDDD, Art. 27].",
    citations: [
      { framework: 'CSDDD', reference: 'Art. 2(1)', quote_snippet: 'This Directive shall apply to companies with more than 1,000 employees...' },
      { framework: 'CSDDD', reference: 'Art. 7', quote_snippet: 'Member States shall ensure that companies take appropriate measures to identify...' },
      { framework: 'CSDDD', reference: 'Art. 22', quote_snippet: 'Companies shall adopt a transition plan for climate change mitigation...' },
    ],
    confidence_score: 0.90,
    requires_expert_review: false,
    related_frameworks: ['CSRD', 'EU Taxonomy'],
    caveats: ['La proposta Omnibus I potrebbe innalzare le soglie e posticipare i termini di trasposizione.'],
  },
  cross_ai_gdpr: {
    answer: "**Sotto l'AI Act:**\nI sistemi di AI utilizzati per il credit scoring sono classificati come **alto rischio** [AI Act, Art. 6, Annex III §5(b)]. Questo comporta obblighi di: gestione del rischio [Art. 9], governance dei dati di training [Art. 10], trasparenza verso l'utente [Art. 13], e supervisione umana [Art. 14]. Il deployer deve eseguire una valutazione d'impatto sui diritti fondamentali [Art. 27].\n\n**Sotto il GDPR:**\nIl credit scoring basato su AI costituisce un **processo decisionale automatizzato** soggetto all'Art. 22 GDPR. L'interessato ha diritto a: non essere soggetto a decisioni basate unicamente su trattamento automatizzato [Art. 22(1)], ottenere l'intervento umano [Art. 22(3)], e ricevere informazioni significative sulla logica del trattamento [Art. 13(2)(f)].\n\n**Interazione tra i due framework:**\nL'Art. 2(7) dell'AI Act stabilisce che il GDPR resta pienamente applicabile. In pratica, per un sistema di credit scoring basato su AI servono ENTRAMBE le conformità: la DPIA del GDPR [Art. 35] e la valutazione d'impatto AI Act [Art. 27], la supervisione umana sia per Art. 22 GDPR che per Art. 14 AI Act.",
    citations: [
      { framework: 'AI Act', reference: 'Art. 6, Annex III', quote_snippet: 'AI systems intended to be used for credit scoring shall be considered high-risk...' },
      { framework: 'AI Act', reference: 'Art. 27', quote_snippet: 'Deployers of high-risk AI systems shall perform a fundamental rights impact assessment...' },
      { framework: 'GDPR', reference: 'Art. 22(1)', quote_snippet: 'The data subject shall have the right not to be subject to a decision based solely on automated processing...' },
      { framework: 'GDPR', reference: 'Art. 35(3)', quote_snippet: 'A data protection impact assessment shall be required in particular for systematic evaluation of personal aspects...' },
    ],
    confidence_score: 0.88,
    requires_expert_review: false,
    related_frameworks: ['DORA'],
    caveats: ['L\'interazione precisa tra AI Act e GDPR per il credit scoring sarà chiarita dalle linee guida dell\'AI Office e dell\'EDPB.'],
  },
  cross_dora_nis2: {
    answer: "**Sotto DORA:**\nDORA (Reg. 2022/2554) è la lex specialis per la resilienza operativa digitale del settore finanziario. Obblighi chiave: framework ICT risk management [Art. 6], incident reporting entro 4 ore [Art. 19], TLPT testing ogni 3 anni [Art. 26], gestione rischio fornitori ICT [Art. 28-44].\n\n**Sotto NIS2:**\nLa Direttiva NIS2 (2022/2555) copre la cybersecurity per settori essenziali e importanti. Obblighi chiave: misure di gestione del rischio [Art. 21], incident reporting in 3 fasi (24h/72h/1 mese) [Art. 23], governance della sicurezza [Art. 20].\n\n**Rapporto tra i due framework:**\nL'Art. 4 della NIS2 stabilisce la **clausola lex specialis**: quando un atto settoriale dell'UE (come DORA) impone requisiti almeno equivalenti, le disposizioni NIS2 non si applicano a quelle entità. Per le **entità finanziarie soggette a DORA, gli obblighi NIS2 sono sostituiti da DORA** [NIS2, Art. 4(2)]. Tuttavia:\n- Se l'entità finanziaria opera anche in settori coperti da NIS2 (es. cloud provider), può essere soggetta a entrambi\n- I CSIRT nazionali NIS2 collaborano con le autorità finanziarie per l'information sharing [DORA, Art. 45]",
    citations: [
      { framework: 'DORA', reference: 'Art. 6(1)', quote_snippet: 'Financial entities shall have a sound, comprehensive ICT risk management framework...' },
      { framework: 'NIS2', reference: 'Art. 4(2)', quote_snippet: 'Where a sector-specific act requires measures at least equivalent in effect, those provisions shall apply...' },
      { framework: 'DORA', reference: 'Art. 19(1)', quote_snippet: 'Financial entities shall classify and report major ICT-related incidents...' },
      { framework: 'NIS2', reference: 'Art. 23(4)', quote_snippet: 'The early warning, incident notification and final report shall contain...' },
    ],
    confidence_score: 0.93,
    requires_expert_review: false,
    related_frameworks: ['GDPR'],
    caveats: ['La clausola lex specialis è soggetta a valutazione caso per caso da parte delle autorità nazionali.'],
  },
  // ─── Article-specific responses ──────────────────────────
  gdpr_art17: {
    answer: "**Art. 17 GDPR — Diritto alla cancellazione (\"diritto all'oblio\")**\n\nL'Art. 17 del GDPR (Reg. 2016/679) stabilisce il diritto dell'interessato di ottenere dal titolare del trattamento la cancellazione dei dati personali che lo riguardano senza ingiustificato ritardo. Il titolare ha l'obbligo di cancellare i dati personali quando:\n\n1. **Finalità esaurita** — I dati non sono più necessari rispetto alle finalità per cui sono stati raccolti [Art. 17(1)(a)]\n2. **Revoca del consenso** — L'interessato revoca il consenso su cui si basa il trattamento e non esiste altra base giuridica [Art. 17(1)(b)]\n3. **Opposizione al trattamento** — L'interessato si oppone al trattamento ex Art. 21 e non sussistono motivi legittimi prevalenti [Art. 17(1)(c)]\n4. **Trattamento illecito** — I dati sono stati trattati illecitamente [Art. 17(1)(d)]\n5. **Obbligo legale** — La cancellazione è necessaria per adempiere un obbligo legale UE o nazionale [Art. 17(1)(e)]\n\n**Eccezioni** [Art. 17(3)]: Il diritto alla cancellazione non si applica quando il trattamento è necessario per l'esercizio del diritto alla libertà di espressione, per motivi di interesse pubblico nel settore della sanità, o per l'accertamento/esercizio/difesa di un diritto in sede giudiziaria.\n\n**Obbligo di comunicazione ai terzi** [Art. 17(2)]: Se il titolare ha reso pubblici i dati, deve adottare misure ragionevoli per informare i terzi che trattano tali dati della richiesta di cancellazione.",
    citations: [
      { framework: 'GDPR', reference: 'Art. 17(1)', quote_snippet: 'The data subject shall have the right to obtain from the controller the erasure of personal data...' },
      { framework: 'GDPR', reference: 'Art. 17(2)', quote_snippet: 'The controller shall take reasonable steps to inform controllers processing the personal data...' },
      { framework: 'GDPR', reference: 'Art. 17(3)', quote_snippet: 'The right to erasure shall not apply to the extent that processing is necessary for exercising the right of freedom of expression...' },
    ],
    confidence_score: 0.96,
    requires_expert_review: false,
    related_frameworks: ['AI Act', 'CSDDD'],
    caveats: ['Le eccezioni all\'Art. 17(3) vanno valutate caso per caso con supporto legale.'],
  },
  gdpr_art13: {
    answer: "**Art. 13 GDPR — Informazioni da fornire in caso di raccolta presso l'interessato**\n\nL'Art. 13 del GDPR (Reg. 2016/679) stabilisce gli obblighi informativi del titolare quando i dati personali sono raccolti direttamente dall'interessato. Il titolare deve fornire le seguenti informazioni al momento della raccolta:\n\n1. **Identità del titolare** — Nome e dati di contatto del titolare e del DPO [Art. 13(1)(a-b)]\n2. **Finalità e base giuridica** — Le finalità del trattamento e la base giuridica [Art. 13(1)(c)]\n3. **Destinatari** — I destinatari o le categorie di destinatari dei dati [Art. 13(1)(e)]\n4. **Trasferimenti extra-UE** — L'intenzione di trasferire dati verso paesi terzi [Art. 13(1)(f)]\n5. **Periodo di conservazione** — Il periodo di conservazione o i criteri per determinarlo [Art. 13(2)(a)]\n6. **Diritti dell'interessato** — Accesso, rettifica, cancellazione, limitazione, portabilità, opposizione [Art. 13(2)(b)]\n7. **Processo decisionale automatizzato** — Informazioni significative sulla logica utilizzata e sulle conseguenze previste [Art. 13(2)(f)]\n\nLe informazioni devono essere fornite in forma **concisa, trasparente, intelligibile e facilmente accessibile**, con un linguaggio semplice e chiaro [Art. 12(1)].",
    citations: [
      { framework: 'GDPR', reference: 'Art. 13(1)', quote_snippet: 'Where personal data relating to a data subject are collected from the data subject, the controller shall provide the following information...' },
      { framework: 'GDPR', reference: 'Art. 13(2)', quote_snippet: 'The controller shall provide the data subject with the following further information necessary to ensure fair and transparent processing...' },
      { framework: 'GDPR', reference: 'Art. 12(1)', quote_snippet: 'The controller shall take appropriate measures to provide any information referred to in Articles 13 and 14 in a concise, transparent, intelligible and easily accessible form...' },
    ],
    confidence_score: 0.95,
    requires_expert_review: false,
    related_frameworks: ['AI Act'],
    caveats: [],
  },
  ai_act_art9: {
    answer: "**Art. 9 AI Act — Sistema di gestione dei rischi**\n\nL'Art. 9 del Regolamento AI Act (2024/1689) stabilisce l'obbligo per i provider di sistemi di AI ad alto rischio di istituire, implementare, documentare e mantenere un **sistema di gestione dei rischi** durante l'intero ciclo di vita del sistema.\n\nIl sistema di gestione dei rischi deve includere:\n\n1. **Identificazione e analisi dei rischi** — Identificare e analizzare i rischi noti e ragionevolmente prevedibili per la salute, la sicurezza e i diritti fondamentali [Art. 9(2)(a)]\n2. **Stima e valutazione** — Stimare e valutare i rischi che possono emergere dall'uso conforme e dall'uso improprio ragionevolmente prevedibile [Art. 9(2)(b)]\n3. **Misure di gestione** — Adottare misure di gestione del rischio appropriate, incluse la progettazione e lo sviluppo del sistema [Art. 9(4)]\n4. **Test** — Testare il sistema per identificare le misure più appropriate [Art. 9(5-7)]\n5. **Rischi residui** — I rischi residui devono essere comunicati agli utenti [Art. 9(4)(c)]\n\nIl sistema di gestione dei rischi è un **processo iterativo continuo** che deve essere aggiornato regolarmente durante l'intero ciclo di vita del sistema AI [Art. 9(1)]. Le misure devono tenere conto degli effetti e della possibile interazione con altri sistemi AI [Art. 9(8)].",
    citations: [
      { framework: 'AI Act', reference: 'Art. 9(1)', quote_snippet: 'A risk management system shall be established, implemented, documented and maintained in relation to high-risk AI systems...' },
      { framework: 'AI Act', reference: 'Art. 9(2)', quote_snippet: 'The risk management system shall be a continuous iterative process planned and run throughout the entire lifecycle...' },
      { framework: 'AI Act', reference: 'Art. 9(4)', quote_snippet: 'Risk management measures shall give due consideration to the effects and possible interactions resulting from combined application...' },
    ],
    confidence_score: 0.93,
    requires_expert_review: false,
    related_frameworks: ['GDPR'],
    caveats: ['I dettagli implementativi saranno chiariti dagli standard armonizzati e dalle linee guida dell\'AI Office.'],
  },
  gdpr_art9: {
    answer: "**Art. 9 GDPR — Trattamento di categorie particolari di dati personali**\n\nL'Art. 9 del GDPR (Reg. 2016/679) disciplina il trattamento delle **categorie particolari di dati personali** (cd. \"dati sensibili\").\n\n**Art. 9(1) — Divieto generale:**\nE' vietato trattare dati personali che rivelino:\n- **Origine razziale o etnica**\n- **Opinioni politiche**\n- **Convinzioni religiose o filosofiche**\n- **Appartenenza sindacale**\n- **Dati genetici**\n- **Dati biometrici** (per identificare in modo univoco una persona)\n- **Dati relativi alla salute**\n- **Dati relativi alla vita sessuale o all'orientamento sessuale**\n\n**Art. 9(2) — Eccezioni al divieto:**\nIl trattamento e' consentito quando:\n1. **Consenso esplicito** dell'interessato per finalita' specifiche [Art. 9(2)(a)]\n2. **Diritto del lavoro e sicurezza sociale** — necessario per adempiere obblighi in materia di diritto del lavoro [Art. 9(2)(b)]\n3. **Interessi vitali** — protezione degli interessi vitali dell'interessato quando incapace di prestare consenso [Art. 9(2)(c)]\n4. **Attivita' di fondazioni/associazioni** — trattamento da parte di organismi senza scopo di lucro [Art. 9(2)(d)]\n5. **Dati resi manifestamente pubblici** dall'interessato [Art. 9(2)(e)]\n6. **Azione in giudizio** — accertamento, esercizio o difesa di un diritto [Art. 9(2)(f)]\n7. **Interesse pubblico rilevante** — sulla base del diritto UE o nazionale [Art. 9(2)(g)]\n8. **Finalita' di medicina preventiva o del lavoro** — diagnosi, assistenza sanitaria [Art. 9(2)(h)]\n9. **Sanita' pubblica** — interesse pubblico nel settore della sanita' [Art. 9(2)(i)]\n10. **Archiviazione, ricerca scientifica, statistica** [Art. 9(2)(j)]\n\n**Art. 9(4):** Gli Stati membri possono introdurre ulteriori condizioni, anche limitazioni, per il trattamento di dati genetici, biometrici o relativi alla salute.\n\nLe violazioni dell'Art. 9 sono soggette alle sanzioni massime: fino a **20 milioni di euro** o il **4% del fatturato globale** [Art. 83(5)].",
    citations: [
      { framework: 'GDPR', reference: 'Art. 9(1)', quote_snippet: 'Processing of personal data revealing racial or ethnic origin, political opinions, religious or philosophical beliefs, trade union membership, genetic data, biometric data, data concerning health or sex life or sexual orientation shall be prohibited.' },
      { framework: 'GDPR', reference: 'Art. 9(2)', quote_snippet: 'Paragraph 1 shall not apply if one of the following applies: the data subject has given explicit consent...' },
      { framework: 'GDPR', reference: 'Art. 9(4)', quote_snippet: 'Member States may maintain or introduce further conditions, including limitations, with regard to the processing of genetic data, biometric data or data concerning health.' },
    ],
    confidence_score: 0.96,
    requires_expert_review: false,
    related_frameworks: ['AI Act', 'NIS2'],
    caveats: ['Le eccezioni dell\'Art. 9(2) richiedono una valutazione caso per caso. Consultare il DPO per l\'applicazione concreta.'],
  },
  dora_art30: {
    answer: "**Art. 30 DORA — Disposizioni contrattuali chiave per i fornitori ICT**\n\nL'Art. 30 del Regolamento DORA (2022/2554) stabilisce le **clausole contrattuali obbligatorie** che le entità finanziarie devono includere nei contratti con i fornitori di servizi ICT di terze parti.\n\nI contratti devono includere:\n\n1. **Descrizione delle funzioni** — Descrizione chiara e completa di tutte le funzioni e i servizi ICT [Art. 30(2)(a)]\n2. **Ubicazione dei dati** — Indicazione delle località di trattamento e conservazione dei dati, con obbligo di notifica preventiva in caso di modifica [Art. 30(2)(b)]\n3. **Disponibilità e qualità** — Disposizioni su disponibilità, autenticità, integrità e riservatezza dei dati [Art. 30(2)(c)]\n4. **Diritti di accesso e audit** — Diritti di accesso, ispezione e audit illimitati da parte dell'entità finanziaria e delle autorità [Art. 30(2)(e)]\n5. **Livelli di servizio** — SLA chiari con indicatori quantitativi e qualitativi [Art. 30(3)]\n6. **Incident reporting** — Obblighi di assistenza e notifica in caso di incidenti ICT [Art. 30(2)(f)]\n7. **Exit strategy** — Piani e periodi di transizione adeguati per garantire la continuità in caso di cessazione [Art. 30(2)(g)]\n8. **Subappalto** — Condizioni per il subappalto, incluso il diritto di opporsi [Art. 30(2)(a)]\n\nPer i fornitori che supportano **funzioni critiche o importanti**, si applicano requisiti aggiuntivi più stringenti [Art. 30(3)].",
    citations: [
      { framework: 'DORA', reference: 'Art. 30(2)', quote_snippet: 'The contractual arrangements on the use of ICT services shall include at least the following key contractual provisions...' },
      { framework: 'DORA', reference: 'Art. 30(3)', quote_snippet: 'When contractual arrangements relate to ICT services supporting critical or important functions, the contracts shall also include...' },
      { framework: 'DORA', reference: 'Art. 28(2)', quote_snippet: 'Financial entities shall manage ICT third-party risk as an integral component of ICT risk...' },
    ],
    confidence_score: 0.94,
    requires_expert_review: false,
    related_frameworks: ['NIS2'],
    caveats: ['Le clausole contrattuali devono essere riviste alla luce degli standard tecnici di regolamentazione (RTS) dell\'EBA.'],
  },
  gdpr_dpo: {
    answer: "**Art. 37-39 GDPR — Il Data Protection Officer (DPO)**\n\nIl DPO è una figura chiave del GDPR (Reg. 2016/679), obbligatoria in specifiche circostanze e dotata di garanzie di indipendenza.\n\n**Quando è obbligatorio nominare un DPO** [Art. 37(1)]:\n1. Il trattamento è effettuato da un'**autorità pubblica o un organismo pubblico** (eccetto le autorità giurisdizionali) [Art. 37(1)(a)]\n2. Le attività principali consistono in trattamenti che richiedono il **monitoraggio regolare e sistematico su larga scala** degli interessati [Art. 37(1)(b)]\n3. Le attività principali consistono nel trattamento su larga scala di **categorie particolari di dati** (Art. 9) o dati relativi a condanne penali (Art. 10) [Art. 37(1)(c)]\n\n**Requisiti del DPO** [Art. 37(5)]:\n- Qualità professionali e conoscenza specialistica della normativa e delle prassi in materia di protezione dati\n- Può essere un dipendente interno o un consulente esterno con contratto di servizi [Art. 37(6)]\n- Può essere condiviso da un gruppo di imprese, purché facilmente raggiungibile [Art. 37(2-4)]\n\n**Posizione e indipendenza** [Art. 38]:\n- Il titolare deve garantire che il DPO sia **tempestivamente e adeguatamente coinvolto** in tutte le questioni relative alla protezione dati [Art. 38(1)]\n- Il DPO **non riceve istruzioni** per quanto riguarda l'esecuzione dei suoi compiti [Art. 38(3)]\n- **Non può essere rimosso o penalizzato** per l'adempimento dei suoi compiti [Art. 38(3)]\n- Riferisce direttamente al **vertice gerarchico** del titolare o del responsabile [Art. 38(3)]\n\n**Compiti del DPO** [Art. 39]:\n1. Informare e fornire consulenza al titolare e ai dipendenti sugli obblighi GDPR [Art. 39(1)(a)]\n2. Sorvegliare l'osservanza del GDPR e delle policy interne [Art. 39(1)(b)]\n3. Fornire pareri sulla DPIA e sorvegliarne lo svolgimento [Art. 39(1)(c)]\n4. Cooperare con l'autorità di controllo [Art. 39(1)(d)]\n5. Fungere da punto di contatto con il Garante [Art. 39(1)(e)]",
    citations: [
      { framework: 'GDPR', reference: 'Art. 37(1)', quote_snippet: 'The controller and the processor shall designate a data protection officer in any case where the processing is carried out by a public authority or body...' },
      { framework: 'GDPR', reference: 'Art. 38(3)', quote_snippet: 'The data protection officer shall not receive any instructions regarding the exercise of those tasks. He or she shall not be dismissed or penalised for performing his tasks...' },
      { framework: 'GDPR', reference: 'Art. 39(1)', quote_snippet: 'The data protection officer shall have at least the following tasks: to inform and advise the controller...' },
    ],
    confidence_score: 0.96,
    requires_expert_review: false,
    related_frameworks: ['NIS2', 'AI Act'],
    caveats: ['Le linee guida WP243 del WP29 (ora EDPB) forniscono ulteriori chiarimenti sull\'interpretazione dei criteri di obbligatorietà.'],
  },
  cross_csrd_csddd: {
    answer: "**Sotto il CSRD (Scope 3 / ESRS E1):**\nIl CSRD (Direttiva 2022/2464) richiede la disclosure delle emissioni Scope 1, 2 e **Scope 3** (emissioni indirette della catena del valore) tramite lo standard ESRS E1. Per le imprese del settore energetico, lo Scope 3 è tipicamente il componente più significativo: include emissioni upstream (estrazione, trasporto materie prime) e downstream (uso dei prodotti venduti). L'ESRS E1-6 richiede obiettivi di riduzione coerenti con il percorso 1.5°C [CSRD, Art. 19a; ESRS E1].\n\n**Sotto la CSDDD (Due Diligence sulla Supply Chain):**\nLa CSDDD (Direttiva 2024/1760) impone obblighi di **due diligence sulla catena del valore** per impatti negativi sui diritti umani e l'ambiente [CSDDD, Art. 7-8]. Per il settore energetico, questo include: condizioni lavorative nelle miniere di materie prime, impatto ambientale delle infrastrutture energetiche, e diritti delle comunità locali. L'Art. 22 richiede un **piano di transizione climatica** allineato a 1.5°C.\n\n**Interazione CSRD + CSDDD per Scope 3:**\nI due framework si rafforzano reciprocamente:\n- Lo **Scope 3 CSRD** quantifica le emissioni della catena del valore (reporting)\n- La **due diligence CSDDD** richiede azioni concrete per mitigare gli impatti (azione)\n- Il piano di transizione è richiesto da entrambi (ESRS E1-1 per CSRD, Art. 22 per CSDDD)\n- La mappatura della catena del valore CSDDD alimenta direttamente il calcolo Scope 3\n\nPer un'azienda con 2.500 dipendenti nel settore energy, entrambi i framework sono applicabili e devono essere affrontati in modo integrato.",
    citations: [
      { framework: 'CSRD', reference: 'ESRS E1-6', quote_snippet: 'The undertaking shall disclose its gross Scope 1, 2, and 3 GHG emissions...' },
      { framework: 'CSRD', reference: 'Art. 19a(2)', quote_snippet: 'The sustainability reporting shall contain information on the due diligence process...' },
      { framework: 'CSDDD', reference: 'Art. 7-8', quote_snippet: 'Companies shall take appropriate measures to identify actual and potential adverse impacts...' },
      { framework: 'CSDDD', reference: 'Art. 22', quote_snippet: 'Companies shall adopt a transition plan for climate change mitigation aligned with 1.5°C...' },
    ],
    confidence_score: 0.90,
    requires_expert_review: false,
    related_frameworks: ['EU Taxonomy'],
    caveats: ['L\'interazione CSRD-CSDDD è soggetta alle modifiche del pacchetto Omnibus I in fase di negoziazione.'],
  },
}

const LANGUAGE_NAMES: Record<string, string> = { en: 'English', it: 'italiano', de: 'Deutsch', fr: 'français', es: 'español' }

export function getMockQAResponse(question: string, language: string = 'it'): QAResponse {
  const q = question.toLowerCase()

  // Article-specific detection (check first — most specific)
  let response: QAResponse

  // Extract article number from various patterns: "Art. 17", "Art.17", "Art 17", "Articolo 17", "Article 17", standalone "17"
  const artNumMatch = q.match(/(?:art(?:\.?|icol[eo]|icle)\s*)(\d+)/i) || q.match(/\b(\d{1,3})\b/)
  const artNum = artNumMatch ? parseInt(artNumMatch[1]) : 0
  const hasGdpr = q.includes('gdpr') || q.includes('protezione dati') || q.includes('data protection') || q.includes('privacy')
  const hasAiAct = q.includes('ai act') || q.includes('intelligenza artificiale')
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

  // Cross-framework detection (check next — more specific than single framework)
  else if ((q.includes('ai act') || q.includes('artificial intelligence')) && (q.includes('gdpr') || q.includes('data protection') || q.includes('credit scor')))
    response = QA_RESPONSES.cross_ai_gdpr
  else if ((q.includes('dora') || q.includes('digital operational') || q.includes('resilienza')) && (q.includes('nis2') || q.includes('nis 2') || q.includes('sicurezza informatica')))
    response = QA_RESPONSES.cross_dora_nis2
  else if ((q.includes('csrd') || q.includes('scope 3') || q.includes('sustainability reporting') || q.includes('rendicontazione')) && (q.includes('csddd') || q.includes('due diligence') || q.includes('supply chain') || q.includes('catena')))
    response = QA_RESPONSES.cross_csrd_csddd
  else if ((q.includes('csddd') || q.includes('catena del valore') || q.includes('supply chain')) && (q.includes('csrd') || q.includes('scope 3') || q.includes('esrs')))
    response = QA_RESPONSES.cross_csrd_csddd

  // DPO-specific (before generic GDPR)
  else if (q.includes('dpo') || q.includes('data protection officer') || q.includes('responsabile protezione') || ((q.includes('gdpr') || q.includes('protezione dati')) && (q.includes('art. 37') || q.includes('art.37') || q.includes('art 37') || q.includes('art. 38') || q.includes('art. 39'))))
    response = QA_RESPONSES.gdpr_dpo

  // Single framework
  else if (q.includes('ai act') || q.includes('artificial intelligence') || q.includes('intelligenza artificiale') || q.includes('alto rischio'))
    response = QA_RESPONSES.ai_act
  else if (q.includes('gdpr') || q.includes('data protection') || q.includes('protezione dati') || q.includes('privacy') || q.includes('dati personali'))
    response = QA_RESPONSES.gdpr
  else if (q.includes('dora') || q.includes('digital operational') || q.includes('resilience') || q.includes('resilienza'))
    response = QA_RESPONSES.dora
  else if (q.includes('nis2') || q.includes('nis 2') || q.includes('incident reporting') || q.includes('cybersecurity') || q.includes('sicurezza informatica') || q.includes('meldepflicht'))
    response = QA_RESPONSES.nis2
  else if (q.includes('taxonomy') || q.includes('tassonomia') || q.includes('attività sostenibil'))
    response = QA_RESPONSES.taxonomy
  else if (q.includes('csddd') || q.includes('due diligence') || q.includes('catena del valore') || q.includes('supply chain'))
    response = QA_RESPONSES.csddd
  else if (q.includes('csrd') || q.includes('sustainability reporting') || q.includes('rendicontazione'))
    response = QA_RESPONSES.csrd
  else {
    // Fallback: honest "not covered"
    response = {
      answer: "La tua domanda non corrisponde a uno degli scenari pre-configurati della modalità demo. In modalità live (con backend attivo), NormaAI analizza la tua domanda tramite ricerca semantica su 14.503 chunks di regolamenti EU e genera una risposta con citazioni precise.\n\nProva con una di queste domande:\n- \"Quali sono gli obblighi principali del CSRD?\"\n- \"AI Act e GDPR: overlap per credit scoring\"\n- \"DORA e NIS2: differenze per il settore finanziario\"\n- \"CSRD e CSDDD: obblighi supply chain e Scope 3\"",
      citations: [],
      confidence_score: 0.0,
      requires_expert_review: false,
      related_frameworks: ['CSRD', 'DORA', 'AI_ACT', 'NIS2', 'GDPR', 'CSDDD', 'TAXONOMY'],
      caveats: ['Questa è una risposta demo. Attiva il backend per risposte personalizzate con RAG.'],
    }
  }

  // Language-aware: add caveat when not Italian (mock responses are in IT)
  if (language && language !== 'it') {
    const langName = LANGUAGE_NAMES[language] || language.toUpperCase()
    return {
      ...response,
      caveats: [
        ...(response.caveats || []),
        `Lingua selezionata: ${langName}. In modalità demo le risposte sono in italiano. In produzione, NormaAI risponde nella lingua richiesta (${langName}).`,
      ],
    }
  }

  return response
}

// ─── Gap Analysis Mocks — framework-specific ────────────────

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
      'Prioritize double materiality assessment — required before all ESRS disclosures',
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

// ─── Monitor Mock — input-aware ─────────────────────────────

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
  { id: 'demo-c1', name: 'EnergiePlus GmbH', sector: 'Energy', employee_count: 5000, revenue_eur: 800_000_000, jurisdictions: ['DE', 'AT', 'PL'], applicable_frameworks: ['CSRD', 'CSDDD', 'EU Taxonomy', 'NIS2'] },
  { id: 'demo-c2', name: 'Banca Meridiana S.p.A.', sector: 'Financial Services', employee_count: 3200, revenue_eur: 1_200_000_000, jurisdictions: ['IT', 'ES'], applicable_frameworks: ['DORA', 'NIS2', 'GDPR', 'CSRD'] },
  { id: 'demo-c3', name: 'MedTech Innovations B.V.', sector: 'Healthcare / Technology', employee_count: 1800, revenue_eur: 350_000_000, jurisdictions: ['NL', 'DE', 'FR'], applicable_frameworks: ['AI_ACT', 'GDPR', 'CSRD'] },
  { id: 'demo-c4', name: 'LogiTrans Europe S.A.', sector: 'Transport & Logistics', employee_count: 4500, revenue_eur: 600_000_000, jurisdictions: ['FR', 'BE', 'LU', 'DE'], applicable_frameworks: ['CSRD', 'NIS2', 'CSDDD', 'EU Taxonomy'] },
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
  { id: '1', title: 'CSRD reporting deadline approaching — Q1 2026 submissions', description: 'First wave of CSRD reports due for large undertakings. Ensure ESRS-aligned sustainability statement is ready for annual report.', severity: 'CRITICAL', framework: 'CSRD', is_read: false, is_dismissed: false, created_at: new Date().toISOString(), source: 'EU Official Journal', client_id: null, regulation_id: null, actions_required: ['Finalize double materiality assessment', 'Complete ESRS data collection'], deadline: '2026-03-31' },
  { id: '2', title: 'DORA ICT risk framework compliance deadline passed', description: 'DORA became applicable January 17, 2025. ESA Joint Committee published updated RTS/ITS requiring immediate action on ICT third-party risk management.', severity: 'HIGH', framework: 'DORA', is_read: false, is_dismissed: false, created_at: new Date(Date.now() - 86400000).toISOString(), source: 'ESA Joint Committee', client_id: null, regulation_id: null, actions_required: ['Review ICT contracts', 'Update incident reporting process'], deadline: '2025-07-17' },
  { id: '3', title: 'AI Act high-risk classification guidance published', description: 'The AI Office released detailed guidance on Annex III high-risk AI system classification. Companies deploying AI in HR, credit scoring, or critical infrastructure should review.', severity: 'MEDIUM', framework: 'AI_ACT', is_read: true, is_dismissed: false, created_at: new Date(Date.now() - 172800000).toISOString(), source: 'AI Office', client_id: null, regulation_id: null, actions_required: ['Inventory AI systems', 'Classify by risk level'], deadline: '2026-08-02' },
  { id: '4', title: 'NIS2 transposition — sector scope clarification for manufacturing', description: 'ENISA published guidance clarifying NIS2 applicability for manufacturing entities in Annex II. Companies above 250 employees in critical sectors must register.', severity: 'LOW', framework: 'NIS2', is_read: true, is_dismissed: false, created_at: new Date(Date.now() - 432000000).toISOString(), source: 'ENISA', client_id: null, regulation_id: null, actions_required: ['Check entity classification'], deadline: null },
  { id: '5', title: 'EU Taxonomy delegated acts update — new screening criteria', description: 'European Commission adopted new delegated acts extending technical screening criteria to additional economic activities under environmental objectives 3-6.', severity: 'INFORMATIONAL', framework: 'TAXONOMY', is_read: true, is_dismissed: false, created_at: new Date(Date.now() - 604800000).toISOString(), source: 'European Commission', client_id: null, regulation_id: null, actions_required: [], deadline: null },
]

export const DEMO_ALERT_SUMMARY = {
  total: 5,
  unread: 2,
  by_severity: { CRITICAL: 1, HIGH: 1, MEDIUM: 1, LOW: 1, INFORMATIONAL: 1 } as Record<string, number>,
  by_framework: { CSRD: 1, DORA: 1, AI_ACT: 1, NIS2: 1, TAXONOMY: 1 } as Record<string, number>,
}

// ─── Audit Trail Mocks ─────────────────────────────────────

export const DEMO_AUDIT_EVENTS: AuditEvent[] = [
  { id: 'audit-001', timestamp: '2026-03-02T14:32:00Z', user_id: 'demo-user-001', user_name: 'Demo User', user_email: 'demo@normaai.eu', action: 'qa.query', resource_type: 'qa', details: 'Q&A query: "Obblighi CSRD per aziende con >250 dipendenti"', ip_address: '192.168.1.100', framework: 'CSRD' },
  { id: 'audit-002', timestamp: '2026-03-02T14:28:00Z', user_id: 'demo-user-001', user_name: 'Demo User', user_email: 'demo@normaai.eu', action: 'gap_analysis.run', resource_type: 'gap_analysis', resource_id: 'ga-001', details: 'Gap Analysis DORA — Score: 72%', ip_address: '192.168.1.100', framework: 'DORA' },
  { id: 'audit-003', timestamp: '2026-03-02T13:55:00Z', user_id: 'user-002', user_name: 'Maria Bianchi', user_email: 'maria@company.eu', action: 'report.generate', resource_type: 'report', resource_id: 'rpt-001', details: 'Report HTML generato — CSRD Compliance Report', ip_address: '10.0.0.45', framework: 'CSRD' },
  { id: 'audit-004', timestamp: '2026-03-02T13:42:00Z', user_id: 'user-002', user_name: 'Maria Bianchi', user_email: 'maria@company.eu', action: 'monitor.analyze', resource_type: 'monitor', details: 'Impact analysis: Omnibus I Package soglie CSRD', ip_address: '10.0.0.45', framework: 'CSRD' },
  { id: 'audit-005', timestamp: '2026-03-02T12:15:00Z', user_id: 'demo-user-001', user_name: 'Demo User', user_email: 'demo@normaai.eu', action: 'client.create', resource_type: 'client', resource_id: 'cli-001', details: 'Nuovo client: Banca Meridiana S.p.A.', ip_address: '192.168.1.100' },
  { id: 'audit-006', timestamp: '2026-03-02T11:30:00Z', user_id: 'user-003', user_name: 'Luca Verdi', user_email: 'luca@company.eu', action: 'alert.dismiss', resource_type: 'alert', resource_id: 'alert-002', details: 'Alert NIS2 marcato come risolto', ip_address: '10.0.0.22', framework: 'NIS2' },
  { id: 'audit-007', timestamp: '2026-03-02T10:05:00Z', user_id: 'demo-user-001', user_name: 'Demo User', user_email: 'demo@normaai.eu', action: 'auth.login', resource_type: 'auth', details: 'Login demo mode', ip_address: '192.168.1.100' },
  { id: 'audit-008', timestamp: '2026-03-01T16:48:00Z', user_id: 'user-002', user_name: 'Maria Bianchi', user_email: 'maria@company.eu', action: 'qa.query', resource_type: 'qa', details: 'Q&A query: "GDPR Art. 17 diritto alla cancellazione"', ip_address: '10.0.0.45', framework: 'GDPR' },
  { id: 'audit-009', timestamp: '2026-03-01T15:20:00Z', user_id: 'user-003', user_name: 'Luca Verdi', user_email: 'luca@company.eu', action: 'gap_analysis.run', resource_type: 'gap_analysis', resource_id: 'ga-002', details: 'Gap Analysis NIS2 — Score: 85%', ip_address: '10.0.0.22', framework: 'NIS2' },
  { id: 'audit-010', timestamp: '2026-03-01T14:00:00Z', user_id: 'demo-user-001', user_name: 'Demo User', user_email: 'demo@normaai.eu', action: 'document.upload', resource_type: 'document', resource_id: 'doc-001', details: 'Upload documento: Politica_ICT_Risk_v2.pdf', ip_address: '192.168.1.100' },
  { id: 'audit-011', timestamp: '2026-03-01T11:30:00Z', user_id: 'user-002', user_name: 'Maria Bianchi', user_email: 'maria@company.eu', action: 'report.export', resource_type: 'report', resource_id: 'rpt-002', details: 'Export PDF — Gap Analysis AI Act Report', ip_address: '10.0.0.45', framework: 'AI_ACT' },
  { id: 'audit-012', timestamp: '2026-03-01T09:15:00Z', user_id: 'user-003', user_name: 'Luca Verdi', user_email: 'luca@company.eu', action: 'auth.login', resource_type: 'auth', details: 'Login standard', ip_address: '10.0.0.22' },
  { id: 'audit-013', timestamp: '2026-02-28T17:30:00Z', user_id: 'demo-user-001', user_name: 'Demo User', user_email: 'demo@normaai.eu', action: 'client.update', resource_type: 'client', resource_id: 'cli-001', details: 'Aggiornato profilo: Banca Meridiana S.p.A.', ip_address: '192.168.1.100' },
  { id: 'audit-014', timestamp: '2026-02-28T15:00:00Z', user_id: 'user-002', user_name: 'Maria Bianchi', user_email: 'maria@company.eu', action: 'monitor.analyze', resource_type: 'monitor', details: 'Impact analysis: DORA ICT third-party risk requirements', ip_address: '10.0.0.45', framework: 'DORA' },
  { id: 'audit-015', timestamp: '2026-02-28T10:45:00Z', user_id: 'user-003', user_name: 'Luca Verdi', user_email: 'luca@company.eu', action: 'system.config_change', resource_type: 'system', details: 'Configurazione alert: soglia CRITICAL modificata', ip_address: '10.0.0.22' },
]

// ─── RBAC Mock Data ─────────────────────────────────────────

export const DEMO_ROLES: Role[] = [
  {
    id: 'role-admin',
    name: 'Administrator',
    description: 'Accesso completo a tutte le funzionalità e configurazioni di sistema',
    permissions: [
      'qa.query', 'qa.export',
      'gap_analysis.run', 'gap_analysis.approve',
      'monitor.analyze', 'monitor.configure',
      'reports.generate', 'reports.export', 'reports.approve',
      'alerts.view', 'alerts.manage', 'alerts.configure',
      'clients.view', 'clients.create', 'clients.edit', 'clients.delete',
      'documents.view', 'documents.upload', 'documents.delete',
      'audit.view', 'audit.export',
      'admin.users', 'admin.roles', 'admin.system', 'admin.sso',
    ],
    user_count: 2,
    is_system: true,
    created_at: '2025-01-15T00:00:00Z',
  },
  {
    id: 'role-compliance-officer',
    name: 'Compliance Officer',
    description: 'Analisi, approvazione gap analysis e report, gestione alert',
    permissions: [
      'qa.query', 'qa.export',
      'gap_analysis.run', 'gap_analysis.approve',
      'monitor.analyze',
      'reports.generate', 'reports.export', 'reports.approve',
      'alerts.view', 'alerts.manage',
      'clients.view', 'clients.edit',
      'documents.view', 'documents.upload',
      'audit.view', 'audit.export',
    ],
    user_count: 3,
    is_system: true,
    created_at: '2025-01-15T00:00:00Z',
  },
  {
    id: 'role-analyst',
    name: 'Analyst',
    description: 'Esecuzione analisi Q&A e gap analysis, generazione report (no approvazione)',
    permissions: [
      'qa.query', 'qa.export',
      'gap_analysis.run',
      'monitor.analyze',
      'reports.generate', 'reports.export',
      'alerts.view',
      'clients.view',
      'documents.view', 'documents.upload',
      'audit.view',
    ],
    user_count: 5,
    is_system: true,
    created_at: '2025-01-15T00:00:00Z',
  },
  {
    id: 'role-viewer',
    name: 'Viewer',
    description: 'Sola lettura — visualizzazione report, alert e audit trail',
    permissions: [
      'qa.query',
      'alerts.view',
      'clients.view',
      'documents.view',
      'audit.view',
    ],
    user_count: 8,
    is_system: true,
    created_at: '2025-01-15T00:00:00Z',
  },
  {
    id: 'role-auditor',
    name: 'External Auditor',
    description: 'Accesso audit trail e report per revisori esterni — nessuna modifica',
    permissions: [
      'audit.view', 'audit.export',
      'reports.export',
      'clients.view',
    ],
    user_count: 1,
    is_system: false,
    created_at: '2026-02-10T00:00:00Z',
  },
]

// ─── Client Compliance Mock Data ────────────────────────────

export const DEMO_CLIENT_COMPLIANCE: Record<string, {
  scores: ClientComplianceScore[]
  history: ClientComplianceHistory[]
}> = {
  'Banca Meridiana S.p.A.': {
    scores: [
      { framework: 'DORA', score: 72, previous_score: 45, trend: 'up', last_assessed: '2026-03-01' },
      { framework: 'NIS2', score: 85, previous_score: 78, trend: 'up', last_assessed: '2026-03-01' },
      { framework: 'GDPR', score: 91, previous_score: 88, trend: 'up', last_assessed: '2026-02-15' },
      { framework: 'CSRD', score: 34, previous_score: 20, trend: 'up', last_assessed: '2026-02-20' },
    ],
    history: [
      { month: 'Ott 2025', scores: { DORA: 28, NIS2: 55, GDPR: 82, CSRD: 10 } },
      { month: 'Nov 2025', scores: { DORA: 35, NIS2: 62, GDPR: 84, CSRD: 15 } },
      { month: 'Dic 2025', scores: { DORA: 40, NIS2: 70, GDPR: 86, CSRD: 18 } },
      { month: 'Gen 2026', scores: { DORA: 45, NIS2: 75, GDPR: 88, CSRD: 20 } },
      { month: 'Feb 2026', scores: { DORA: 58, NIS2: 78, GDPR: 88, CSRD: 25 } },
      { month: 'Mar 2026', scores: { DORA: 72, NIS2: 85, GDPR: 91, CSRD: 34 } },
    ],
  },
  'TechCo Italia S.r.l.': {
    scores: [
      { framework: 'AI_ACT', score: 65, previous_score: 40, trend: 'up', last_assessed: '2026-03-01' },
      { framework: 'GDPR', score: 88, previous_score: 85, trend: 'up', last_assessed: '2026-02-28' },
      { framework: 'NIS2', score: 52, previous_score: 48, trend: 'up', last_assessed: '2026-02-25' },
      { framework: 'CSRD', score: 28, previous_score: 15, trend: 'up', last_assessed: '2026-02-20' },
    ],
    history: [
      { month: 'Ott 2025', scores: { AI_ACT: 15, GDPR: 78, NIS2: 30, CSRD: 5 } },
      { month: 'Nov 2025', scores: { AI_ACT: 22, GDPR: 80, NIS2: 35, CSRD: 8 } },
      { month: 'Dic 2025', scores: { AI_ACT: 30, GDPR: 82, NIS2: 40, CSRD: 12 } },
      { month: 'Gen 2026', scores: { AI_ACT: 40, GDPR: 85, NIS2: 48, CSRD: 15 } },
      { month: 'Feb 2026', scores: { AI_ACT: 55, GDPR: 85, NIS2: 48, CSRD: 20 } },
      { month: 'Mar 2026', scores: { AI_ACT: 65, GDPR: 88, NIS2: 52, CSRD: 28 } },
    ],
  },
  'Assicurazioni Alfa S.p.A.': {
    scores: [
      { framework: 'DORA', score: 80, previous_score: 72, trend: 'up', last_assessed: '2026-02-28' },
      { framework: 'GDPR', score: 94, previous_score: 92, trend: 'up', last_assessed: '2026-03-01' },
      { framework: 'CSRD', score: 55, previous_score: 42, trend: 'up', last_assessed: '2026-02-15' },
    ],
    history: [
      { month: 'Ott 2025', scores: { DORA: 50, GDPR: 85, CSRD: 25 } },
      { month: 'Nov 2025', scores: { DORA: 58, GDPR: 87, CSRD: 30 } },
      { month: 'Dic 2025', scores: { DORA: 65, GDPR: 90, CSRD: 35 } },
      { month: 'Gen 2026', scores: { DORA: 72, GDPR: 92, CSRD: 42 } },
      { month: 'Feb 2026', scores: { DORA: 76, GDPR: 92, CSRD: 48 } },
      { month: 'Mar 2026', scores: { DORA: 80, GDPR: 94, CSRD: 55 } },
    ],
  },
}

// ─── Delay helper ───────────────────────────────────────────

export function mockDelay(ms: number = 1500): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms))
}

// ─── Workflow Mock Data ─────────────────────────────────────

export const DEMO_WORKFLOW_ITEMS: WorkflowItem[] = [
  {
    id: 'wf-001',
    title: 'Gap critico: ICT Risk Management Framework assente',
    description: 'DORA Art. 6 richiede un framework di gestione del rischio ICT documentato e approvato dal management body. Attualmente non \u00e8 presente alcuna policy formalizzata.',
    source: 'gap_analysis',
    framework: 'DORA',
    status: 'ai_generated',
    priority: 'P1',
    assigned_to: null,
    assigned_to_name: null,
    created_at: '2026-03-02T10:00:00Z',
    updated_at: '2026-03-02T10:00:00Z',
    deadline: '2026-04-15',
    client_name: 'Banca Meridiana S.p.A.',
    approval_chain: [
      { role: 'Analyst', user: 'Luca Verdi', status: 'pending', date: null },
      { role: 'Team Lead', user: 'Maria Bianchi', status: 'pending', date: null },
      { role: 'Head of Compliance', user: 'Paolo Rossi', status: 'pending', date: null },
    ],
  },
  {
    id: 'wf-002',
    title: 'Reporting CSRD: doppia materialit\u00e0 non implementata',
    description: 'CSRD richiede double materiality assessment (ESRS 1 \u00a738-42). L\'azienda effettua solo materialit\u00e0 finanziaria.',
    source: 'gap_analysis',
    framework: 'CSRD',
    status: 'under_review',
    priority: 'P1',
    assigned_to: 'user-002',
    assigned_to_name: 'Maria Bianchi',
    created_at: '2026-03-01T14:00:00Z',
    updated_at: '2026-03-02T09:30:00Z',
    deadline: '2026-06-30',
    client_name: 'TechCo Italia S.r.l.',
    approval_chain: [
      { role: 'Analyst', user: 'Luca Verdi', status: 'approved', date: '2026-03-01T16:00:00Z' },
      { role: 'Team Lead', user: 'Maria Bianchi', status: 'pending', date: null },
      { role: 'Head of Compliance', user: 'Paolo Rossi', status: 'pending', date: null },
    ],
  },
  {
    id: 'wf-003',
    title: 'NIS2: procedura incident reporting da definire',
    description: 'Art. 23 NIS2 richiede notifica entro 24h per early warning e 72h per full notification. Nessuna procedura documentata.',
    source: 'gap_analysis',
    framework: 'NIS2',
    status: 'validated',
    priority: 'P2',
    assigned_to: 'user-003',
    assigned_to_name: 'Luca Verdi',
    created_at: '2026-02-28T11:00:00Z',
    updated_at: '2026-03-01T15:00:00Z',
    deadline: '2026-05-30',
    client_name: 'Banca Meridiana S.p.A.',
    approval_chain: [
      { role: 'Analyst', user: 'Luca Verdi', status: 'approved', date: '2026-02-28T14:00:00Z' },
      { role: 'Team Lead', user: 'Maria Bianchi', status: 'approved', date: '2026-03-01T15:00:00Z' },
      { role: 'Head of Compliance', user: 'Paolo Rossi', status: 'pending', date: null },
    ],
  },
  {
    id: 'wf-004',
    title: 'AI Act: registro sistema AI ad alto rischio',
    description: 'Art. 49 AI Act richiede registrazione nella banca dati EU per sistemi AI ad alto rischio prima dell\'immissione sul mercato.',
    source: 'monitor',
    framework: 'AI_ACT',
    status: 'approved',
    priority: 'P2',
    assigned_to: 'user-002',
    assigned_to_name: 'Maria Bianchi',
    created_at: '2026-02-25T09:00:00Z',
    updated_at: '2026-02-28T17:00:00Z',
    deadline: '2026-09-01',
    client_name: 'TechCo Italia S.r.l.',
    approval_chain: [
      { role: 'Analyst', user: 'Luca Verdi', status: 'approved', date: '2026-02-25T14:00:00Z' },
      { role: 'Team Lead', user: 'Maria Bianchi', status: 'approved', date: '2026-02-26T10:00:00Z' },
      { role: 'Head of Compliance', user: 'Paolo Rossi', status: 'approved', date: '2026-02-28T17:00:00Z' },
    ],
  },
  {
    id: 'wf-005',
    title: 'GDPR: DPIA non aggiornata per nuovo trattamento',
    description: 'Art. 35 GDPR richiede DPIA per il nuovo sistema di profilazione clienti. DPIA esistente risale al 2023 e non copre il nuovo trattamento.',
    source: 'qa',
    framework: 'GDPR',
    status: 'ai_generated',
    priority: 'P1',
    assigned_to: null,
    assigned_to_name: null,
    created_at: '2026-03-02T11:30:00Z',
    updated_at: '2026-03-02T11:30:00Z',
    deadline: '2026-03-31',
    client_name: 'Banca Meridiana S.p.A.',
    approval_chain: [
      { role: 'Analyst', user: '', status: 'pending', date: null },
      { role: 'Team Lead', user: '', status: 'pending', date: null },
      { role: 'Head of Compliance', user: '', status: 'pending', date: null },
    ],
  },
  {
    id: 'wf-006',
    title: 'DORA: test di resilienza digitale pianificazione',
    description: 'Art. 24-27 DORA richiede programma di test di resilienza operativa digitale, inclusi TLPT (threat-led penetration testing).',
    source: 'gap_analysis',
    framework: 'DORA',
    status: 'under_review',
    priority: 'P2',
    assigned_to: 'user-003',
    assigned_to_name: 'Luca Verdi',
    created_at: '2026-02-27T10:00:00Z',
    updated_at: '2026-03-01T11:00:00Z',
    deadline: '2026-07-15',
    client_name: 'Banca Meridiana S.p.A.',
    approval_chain: [
      { role: 'Analyst', user: 'Luca Verdi', status: 'approved', date: '2026-02-27T16:00:00Z' },
      { role: 'Team Lead', user: 'Maria Bianchi', status: 'pending', date: null },
      { role: 'Head of Compliance', user: 'Paolo Rossi', status: 'pending', date: null },
    ],
  },
]
