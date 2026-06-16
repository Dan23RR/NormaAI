// data.jsx — fixture data for the NormaAI dashboard prototype.
// Numbers are illustrative only.

const FRAMEWORKS = [
  { id: 'CSRD',     name: 'CSRD',         label: 'Corporate Sustainability Reporting',     score: 78, target: 90, articles: 184, gaps: 14, owner: 'ESG',   color: 'var(--fw-csrd)' },
  { id: 'CSDDD',    name: 'CSDDD',        label: 'Due Diligence Direttiva',                score: 41, target: 70, articles: 38,  gaps: 27, owner: 'Legal', color: 'var(--fw-csddd)' },
  { id: 'AI_ACT',   name: 'AI Act',       label: 'EU AI Act — sistemi alto rischio',       score: 63, target: 85, articles: 113, gaps: 19, owner: 'CTO',   color: 'var(--fw-ai_act)' },
  { id: 'DORA',     name: 'DORA',         label: 'Digital Operational Resilience',         score: 88, target: 90, articles: 64,  gaps: 4,  owner: 'CISO',  color: 'var(--fw-dora)' },
  { id: 'NIS2',     name: 'NIS2',         label: 'Security obblighi essenziali',           score: 72, target: 85, articles: 46,  gaps: 11, owner: 'CISO',  color: 'var(--fw-nis2)' },
  { id: 'TAXONOMY', name: 'EU Taxonomy',  label: 'Tassonomia attività sostenibili',        score: 55, target: 75, articles: 92,  gaps: 17, owner: 'CFO',   color: 'var(--fw-taxonomy)' },
  { id: 'GDPR',     name: 'GDPR',         label: 'Privacy & data protection',              score: 94, target: 95, articles: 99,  gaps: 2,  owner: 'DPO',   color: 'var(--fw-gdpr)' },
];

const DEADLINES = [
  { d: 12, m: 'Dic', y: 2026, fw: 'CSRD',     title: 'Primo report ESRS — esercizio 2026',     sub: 'Bozza preliminare interna',     left: '47g', tone: 'warn' },
  { d: 17, m: 'Gen', y: 2027, fw: 'AI_ACT',   title: 'Registro sistemi alto rischio',          sub: 'Aggiornamento trimestrale',     left: '83g', tone: 'info' },
  { d: 28, m: 'Feb', y: 2027, fw: 'DORA',     title: 'Test resilienza ICT TLPT',                sub: 'Coordinamento fornitori',       left: '125g', tone: 'info' },
  { d:  9, m: 'Mar', y: 2027, fw: 'CSDDD',    title: 'Mappatura value chain — Tier 1',         sub: 'Trasposizione Italia in attesa', left: '134g', tone: 'bad' },
  { d: 25, m: 'Mar', y: 2027, fw: 'NIS2',     title: 'Notifica incidenti significativi',       sub: 'Procedura ENISA pronta',        left: '150g', tone: 'good' },
];

const ALERTS = [
  { p: 'p0', fw: 'CSDDD',  title: 'Trasposizione italiana — bozza pubblicata in GU',  ts: '2h fa',  src: 'EUR-Lex', impact: 'Alto' },
  { p: 'p0', fw: 'AI_ACT', title: 'Codice di buone pratiche GPAI — versione finale',  ts: '5h fa',  src: 'AI Office', impact: 'Alto' },
  { p: 'p1', fw: 'CSRD',   title: 'EFRAG: chiarimenti su ESRS E1 emissioni Scope 3',   ts: '1g fa',  src: 'EFRAG',   impact: 'Medio' },
  { p: 'p1', fw: 'DORA',   title: 'ESAs: nuovi RTS subappalto critico approvati',      ts: '1g fa',  src: 'ESAs',    impact: 'Medio' },
  { p: 'p2', fw: 'GDPR',   title: 'EDPB: linee guida pseudonimizzazione v2',           ts: '2g fa',  src: 'EDPB',    impact: 'Basso' },
  { p: 'p2', fw: 'NIS2',   title: 'ACN: aggiornamento perimetro essenziale',           ts: '3g fa',  src: 'ACN',     impact: 'Medio' },
];

const ACTIVITY = [
  { who: 'Marta R.',    what: 'ha completato gap analysis',  on: 'CSRD · ESRS S1',           when: '14:22', tone: 'good' },
  { who: 'Sistema',     what: 'ha indicizzato 412 articoli', on: 'AI Act allegati',          when: '13:08', tone: 'info' },
  { who: 'Davide T.',   what: 'ha aperto ticket',            on: 'CSDDD art. 8 — supplier',  when: '11:51', tone: 'warn' },
  { who: 'Marta R.',    what: 'ha approvato risposta Q&A',   on: 'DORA RTS subappalto',      when: '10:34', tone: 'good' },
  { who: 'Francesca P.',what: 'ha esportato report',         on: 'GDPR — TIA Q4',            when: '09:12', tone: 'info' },
  { who: 'Sistema',     what: 'ha rilevato modifica',        on: 'EFRAG QA #418',            when: '08:45', tone: 'warn' },
];

const QA_RECENT = [
  { q: 'Quali soglie applicano CSRD a una holding non quotata?', fw: 'CSRD',   user: 'Marta R.',     ts: '11 min', conf: 92 },
  { q: 'Obblighi due diligence per fornitori Tier 2 fuori UE?',  fw: 'CSDDD',  user: 'Davide T.',    ts: '34 min', conf: 78 },
  { q: 'GPAI — quando scattano obblighi trasparenza Art. 53?',   fw: 'AI_ACT', user: 'Francesca P.', ts: '1 ora',  conf: 88 },
  { q: 'TLPT DORA — soglia entità significative banche?',         fw: 'DORA',   user: 'Marta R.',     ts: '2 ore',  conf: 95 },
];

const CLIENTS = [
  { name: 'Banca Adriatica',    sector: 'Banking',     size: 'Large',   score: 81, fws: ['DORA','NIS2','GDPR'],         risk: 'Medio' },
  { name: 'Acciaierie Norditalia', sector: 'Industrial', size: 'Large',  score: 64, fws: ['CSRD','CSDDD','TAXONOMY'],    risk: 'Alto' },
  { name: 'MedTech Lombarda',   sector: 'Healthcare',  size: 'Mid',     score: 89, fws: ['GDPR','AI_ACT','NIS2'],       risk: 'Basso' },
  { name: 'Fondazione Verso',   sector: 'Non-profit',  size: 'Small',   score: 72, fws: ['GDPR','CSRD'],                risk: 'Basso' },
  { name: 'Assicurazioni Tirreno', sector: 'Insurance', size: 'Large',  score: 76, fws: ['DORA','GDPR','CSRD'],         risk: 'Medio' },
];

const MONITOR = [
  { src: 'EUR-Lex',      hits: 142, delta: '+18', last: '4 min', health: 'good' },
  { src: 'EFRAG',        hits:  87, delta:  '+3', last: '12 min', health: 'good' },
  { src: 'ESAs (EBA/ESMA/EIOPA)', hits: 53, delta: '+7', last: '22 min', health: 'good' },
  { src: 'AI Office',    hits:  39, delta: '+12', last: '38 min', health: 'good' },
  { src: 'ACN',          hits:  18, delta:  '+2', last: '1h 14m', health: 'warn' },
  { src: 'Garante Privacy', hits: 27, delta: '+1', last: '2h',   health: 'good' },
  { src: 'EDPB',         hits:  21, delta:  '+4', last: '3h',    health: 'good' },
];

const SPARK_REQUESTS = [12,18,22,16,28,34,30,42,38,46,52,48,61,58,64,72,68,79,84,80,92,88,94,101,108,103,118,124,131,127];

window.NormaData = {
  FRAMEWORKS, DEADLINES, ALERTS, ACTIVITY, QA_RECENT, CLIENTS, MONITOR, SPARK_REQUESTS,
};
