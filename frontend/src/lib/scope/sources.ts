/**
 * The legal sources the scope engine and the obligations calendar cite.
 * Every entry comes from a file of this repository (the two public scope
 * checkers, the Codex, the landing page, the prompts, ADR-003 and ADR-004);
 * the repository location is noted next to each one so a reviewer can
 * check it. Nothing here is a legal opinion.
 */
import { eurlexUrl, type Source } from '@/lib/sources'

/** The day these rules and dates were checked against the repository sources. */
export const VERIFIED_ON = '2026-10-23'

export const CODEX_URL = '/codex-post-omnibus-2025-2029.pdf'

function define(id: string, act: string, opts: Partial<Omit<Source, 'id' | 'act' | 'index' | 'status'>> = {}): Source {
  const url = opts.url ?? (opts.celex ? eurlexUrl(opts.celex) : undefined)
  const origin = opts.origin ?? (url ? 'EUR-Lex' : undefined)
  return {
    ...opts,
    id,
    index: 0,
    act,
    status: 'verified',
    verifiedAt: VERIFIED_ON,
    url,
    origin,
  }
}

export const SCOPE_SOURCES = {
  // public/scope-csrd.html (CITE), README.md "Regulatory Context", ADR-003.
  omnibusI: define('omnibus-i', 'Direttiva (UE) 2026/470 (Omnibus I)', {
    article: 'art. 19-bis e art. 29-bis della Direttiva 2013/34/UE, come modificati; in vigore dal 18 marzo 2026',
    celex: '32026L0470',
  }),
  // public/scope-csrd.html (CITE): the CSRD introduced art. 19-bis.
  csrd: define('csrd', 'Direttiva (UE) 2022/2464 (CSRD)', {
    article: 'art. 19-bis Direttiva 2013/34/UE (art. 29-bis per i gruppi)',
    celex: '32022L2464',
  }),
  // Codex p. 12 and p. 16: Italian transposition of the pre-Omnibus CSRD.
  dlgs125: define('dlgs-125-2024', 'D.Lgs. 6 settembre 2024, n. 125', {
    article: 'recepimento italiano della CSRD, testo pre-Omnibus (GU n. 212 del 10 settembre 2024)',
    origin: 'Gazzetta Ufficiale',
  }),
  // Landing page "Fonti", Codex p. 5, ADR-003, prompts/gap_analyst.txt.
  csddd: define('csddd', 'Direttiva (UE) 2024/1760 (CSDDD), modificata dalla Direttiva (UE) 2026/470', {
    article: 'recepimento entro il 26 luglio 2028, prima applicazione dal 26 luglio 2029',
    celex: '32024L1760',
  }),
  // public/scope-aiact.html and src/app/page.tsx.
  aiAct50_1: define('ai-act-50-1', 'Regolamento (UE) 2024/1689 (AI Act)', {
    article: 'art. 50, par. 1',
    celex: '32024R1689',
  }),
  aiAct50_2: define('ai-act-50-2', 'Regolamento (UE) 2024/1689 (AI Act)', {
    article: 'art. 50, par. 2',
    celex: '32024R1689',
  }),
  aiAct50_3: define('ai-act-50-3', 'Regolamento (UE) 2024/1689 (AI Act)', {
    article: 'art. 50, par. 3',
    celex: '32024R1689',
  }),
  aiAct50_4: define('ai-act-50-4', 'Regolamento (UE) 2024/1689 (AI Act)', {
    article: 'art. 50, par. 4',
    celex: '32024R1689',
  }),
  aiAct50_5: define('ai-act-50-5', 'Regolamento (UE) 2024/1689 (AI Act)', {
    article: 'art. 50, par. 5',
    celex: '32024R1689',
  }),
  aiAct113: define('ai-act-113', 'Regolamento (UE) 2024/1689 (AI Act)', {
    article: 'art. 113, applicazione dal 2 agosto 2026',
    celex: '32024R1689',
  }),
  aiAct99: define('ai-act-99', 'Regolamento (UE) 2024/1689 (AI Act)', {
    article: 'art. 99, par. 4 e par. 6 (sanzioni)',
    celex: '32024R1689',
  }),
  aiAct4: define('ai-act-4', 'Regolamento (UE) 2024/1689 (AI Act)', {
    article: 'art. 4, alfabetizzazione in materia di IA',
    celex: '32024R1689',
  }),
  aiAct5: define('ai-act-5', 'Regolamento (UE) 2024/1689 (AI Act)', {
    article: 'art. 5, pratiche vietate',
    celex: '32024R1689',
  }),
  aiActGpai: define('ai-act-gpai', 'Regolamento (UE) 2024/1689 (AI Act)', {
    article: 'Capo V, modelli di IA per finalità generali',
    celex: '32024R1689',
  }),
  aiActHighRisk: define('ai-act-high-risk', 'Regolamento (UE) 2024/1689 (AI Act)', {
    article: 'sistemi ad alto rischio, allegato III e allegato I',
    celex: '32024R1689',
  }),
  legge132: define('legge-132-2025', 'Legge 132/2025', {
    article: 'autorità nazionali per l’AI Act: ACN e AgID',
    origin: 'Normattiva',
  }),
  // ADR-004, prompts/gap_analyst.txt riga 47, scripts/redteam_openrouter.py (art. 14).
  cra: define('cra', 'Regolamento (UE) 2024/2847 (CRA)', {
    article: 'art. 14, segnalazione di vulnerabilità sfruttate e incidenti gravi',
    celex: '32024R2847',
  }),
  craImplementing: define('cra-implementing', 'Regolamento di esecuzione (UE) 2025/2392', {
    article: 'categorie di prodotti importanti e critici',
    celex: '32025R2392',
  }),
  // Codex p. 18 (CELEX stated there).
  nis2: define('nis2', 'Direttiva (UE) 2022/2555 (NIS2)', {
    article: 'in applicazione dal 18 ottobre 2024; D.Lgs. 138/2024',
    celex: '32022L2555',
  }),
  dora: define('dora', 'Regolamento (UE) 2022/2554 (DORA)', {
    article: 'in applicazione dal 17 gennaio 2025',
    celex: '32022R2554',
  }),
  esrs: define('esrs', 'Regolamento delegato (UE) 2023/2772 (ESRS Set 1)', {
    article: 'principi di rendicontazione di sostenibilità',
  }),
  codex: define('codex', 'Codex Post-Omnibus 2025-2029 (NormaAI, v1.0, 28 aprile 2026)', {
    article: 'guida operativa, non parere legale',
    url: CODEX_URL,
    origin: 'Codex NormaAI',
  }),
} as const satisfies Record<string, Source>

/** Returns the sources renumbered 1..n, without duplicates, ready for display. */
export function withIndex(sources: Source[]): Source[] {
  const seen = new Set<string>()
  const unique = sources.filter((s) => {
    if (seen.has(s.id)) return false
    seen.add(s.id)
    return true
  })
  return unique.map((s, i) => ({ ...s, index: i + 1 }))
}

/** "Regolamento (UE) 2024/1689 (AI Act), art. 50, par. 1 (CELEX 32024R1689)" */
export function sourceLine(source: Source): string {
  const parts = [source.act]
  if (source.article) parts.push(source.article)
  let line = parts.join(', ')
  if (source.celex) line += ` (CELEX ${source.celex})`
  if (source.url) line += ` ${source.url}`
  return line
}
