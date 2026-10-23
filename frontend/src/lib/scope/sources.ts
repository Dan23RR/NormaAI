/**
 * The legal sources the scope engine and the obligations calendar cite.
 * Every entry comes from a file of this repository (the two public scope
 * checkers, the Codex, the landing page, the prompts, ADR-003 and ADR-004);
 * the repository location is noted next to each one so a reviewer can
 * check it. The act and the article, in the language of the interface,
 * live in the `ambito.sources` messages. Nothing here is a legal opinion.
 */
import { eurlexLang } from '@/i18n/config'
import type { TextContext } from '@/i18n/types'
import { eurlexUrl, type Source } from '@/lib/sources'

/** The day these rules and dates were checked against the repository sources. */
export const VERIFIED_ON = '2026-10-23'

export const CODEX_URL = '/codex-post-omnibus-2025-2029.pdf'

export type ScopeSourceKey =
  | 'omnibusI'
  | 'csrd'
  | 'dlgs125'
  | 'csddd'
  | 'aiAct50_1'
  | 'aiAct50_2'
  | 'aiAct50_3'
  | 'aiAct50_4'
  | 'aiAct50_5'
  | 'aiAct113'
  | 'aiAct99'
  | 'aiAct4'
  | 'aiAct5'
  | 'aiActGpai'
  | 'aiActHighRisk'
  | 'legge132'
  | 'cra'
  | 'craImplementing'
  | 'nis2'
  | 'dora'
  | 'esrs'
  | 'codex'

/** The structural part of each source: id, CELEX or link, origin. The words come from the messages. */
const DEFINITIONS: Record<ScopeSourceKey, { id: string; celex?: string; url?: string; origin?: string }> = {
  // public/scope-csrd.html (CITE), README.md "Regulatory Context", ADR-003.
  omnibusI: { id: 'omnibus-i', celex: '32026L0470' },
  // public/scope-csrd.html (CITE): the CSRD introduced art. 19-bis.
  csrd: { id: 'csrd', celex: '32022L2464' },
  // Codex p. 12 and p. 16: Italian transposition of the pre-Omnibus CSRD.
  dlgs125: { id: 'dlgs-125-2024', origin: 'Gazzetta Ufficiale' },
  // Landing page "Fonti", Codex p. 5, ADR-003, prompts/gap_analyst.txt.
  csddd: { id: 'csddd', celex: '32024L1760' },
  // public/scope-aiact.html and src/app/page.tsx.
  aiAct50_1: { id: 'ai-act-50-1', celex: '32024R1689' },
  aiAct50_2: { id: 'ai-act-50-2', celex: '32024R1689' },
  aiAct50_3: { id: 'ai-act-50-3', celex: '32024R1689' },
  aiAct50_4: { id: 'ai-act-50-4', celex: '32024R1689' },
  aiAct50_5: { id: 'ai-act-50-5', celex: '32024R1689' },
  aiAct113: { id: 'ai-act-113', celex: '32024R1689' },
  aiAct99: { id: 'ai-act-99', celex: '32024R1689' },
  aiAct4: { id: 'ai-act-4', celex: '32024R1689' },
  aiAct5: { id: 'ai-act-5', celex: '32024R1689' },
  aiActGpai: { id: 'ai-act-gpai', celex: '32024R1689' },
  aiActHighRisk: { id: 'ai-act-high-risk', celex: '32024R1689' },
  legge132: { id: 'legge-132-2025', origin: 'Normattiva' },
  // ADR-004, prompts/gap_analyst.txt riga 47, scripts/redteam_openrouter.py (art. 14).
  cra: { id: 'cra', celex: '32024R2847' },
  craImplementing: { id: 'cra-implementing', celex: '32025R2392' },
  // Codex p. 18 (CELEX stated there).
  nis2: { id: 'nis2', celex: '32022L2555' },
  dora: { id: 'dora', celex: '32022R2554' },
  esrs: { id: 'esrs' },
  codex: { id: 'codex', url: CODEX_URL, origin: 'Codex NormaAI' },
}

/** The sources in the words and the EUR-Lex language of the interface. */
export function scopeSources(ctx: TextContext): Record<ScopeSourceKey, Source> {
  const out = {} as Record<ScopeSourceKey, Source>
  for (const key of Object.keys(DEFINITIONS) as ScopeSourceKey[]) {
    const def = DEFINITIONS[key]
    const url = def.url ?? (def.celex ? eurlexUrl(def.celex, eurlexLang(ctx.locale)) : undefined)
    const origin = def.origin ?? (url ? 'EUR-Lex' : undefined)
    out[key] = {
      id: def.id,
      index: 0,
      act: ctx.t(`ambito.sources.${key}.act`),
      article: ctx.t(`ambito.sources.${key}.article`),
      celex: def.celex,
      url,
      origin,
      status: 'verified',
      verifiedAt: VERIFIED_ON,
    }
  }
  return out
}

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
