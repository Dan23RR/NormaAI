import { FRAMEWORK_META, frameworkLabel } from '@/components/ui/Badge'
import { eurlexUrl, type Source } from '@/lib/sources'
import type { CitationEvent } from '@/hooks/useSSEStream'
import type { ChiediCitation } from './types'

/**
 * The act behind each framework NormaAI covers, with its CELEX number.
 * Used to name the act and to build the EUR-Lex link when the citation
 * itself does not carry them.
 */
export const ACT_BY_FRAMEWORK: Record<string, { act: string; celex: string }> = {
  CSRD: { act: 'Direttiva (UE) 2022/2464', celex: '32022L2464' },
  CSDDD: { act: 'Direttiva (UE) 2024/1760', celex: '32024L1760' },
  AI_ACT: { act: 'Regolamento (UE) 2024/1689', celex: '32024R1689' },
  DORA: { act: 'Regolamento (UE) 2022/2554', celex: '32022R2554' },
  NIS2: { act: 'Direttiva (UE) 2022/2555', celex: '32022L2555' },
  TAXONOMY: { act: 'Regolamento (UE) 2020/852', celex: '32020R0852' },
  GDPR: { act: 'Regolamento (UE) 2016/679', celex: '32016R0679' },
  CRA: { act: 'Regolamento (UE) 2024/2847', celex: '32024R2847' },
  ESRS: { act: 'Regolamento delegato (UE) 2023/2772', celex: '32023R2772' },
}

const FRAMEWORK_BY_CELEX: Record<string, string> = Object.fromEntries(
  Object.entries(ACT_BY_FRAMEWORK).map(([key, v]) => [v.celex, key]),
)

const FRAMEWORK_ALIASES: Record<string, string> = {
  AI_ACT: 'AI_ACT',
  AIACT: 'AI_ACT',
  AI: 'AI_ACT',
  EU_AI_ACT: 'AI_ACT',
  TAXONOMY: 'TAXONOMY',
  EU_TAXONOMY: 'TAXONOMY',
  TASSONOMIA: 'TAXONOMY',
  TASSONOMIA_UE: 'TAXONOMY',
  NIS2: 'NIS2',
  NIS_2: 'NIS2',
  CSRD: 'CSRD',
  CSDDD: 'CSDDD',
  DORA: 'DORA',
  GDPR: 'GDPR',
  CRA: 'CRA',
  ESRS: 'ESRS',
}

/** "AI Act", "EU Taxonomy", "nis 2" -> the canonical framework key. */
export function normalizeFramework(raw: string | null | undefined): string {
  const key = (raw ?? '')
    .trim()
    .toUpperCase()
    .replace(/[\s-]+/g, '_')
  if (!key) return ''
  return FRAMEWORK_ALIASES[key] ?? key
}

/** True for a well-formed CELEX number such as 32024R1689 or 52021PC0206. */
export function isCelex(value: unknown): value is string {
  return typeof value === 'string' && /^[0-9A-Z]\d{4}[A-Z]{1,2}\d{4}(\(\d{2}\))?$/.test(value.trim())
}

/**
 * True for an http(s) URL that points somewhere: the backend defaults a
 * missing link to "https://eur-lex.europa.eu/eli/" with nothing after it.
 */
export function isUsefulUrl(value: unknown): value is string {
  if (typeof value !== 'string') return false
  try {
    const u = new URL(value)
    if (u.protocol !== 'http:' && u.protocol !== 'https:') return false
    if (/\/eli\/?$/.test(u.pathname) && !u.search) return false
    if (/CELEX:?$/i.test(u.search)) return false
    return true
  } catch {
    return false
  }
}

export function originOf(url: string | undefined): string | undefined {
  if (!url) return undefined
  try {
    const host = new URL(url).hostname
    if (host.endsWith('eur-lex.europa.eu')) return 'EUR-Lex'
    if (host.endsWith('normattiva.it')) return 'Normattiva'
  } catch {
    /* no origin */
  }
  return undefined
}

/**
 * The act as the margin names it: the official act plus the familiar short
 * name, e.g. "Regolamento (UE) 2024/1689 (AI Act)". A real document title
 * coming from the backend wins over the table.
 */
export function actLabel(frameworkKey: string, title?: string): string {
  const cleanTitle = (title ?? '').trim()
  if (cleanTitle && normalizeFramework(cleanTitle) !== frameworkKey) return cleanTitle
  const known = ACT_BY_FRAMEWORK[frameworkKey]
  if (known) return `${known.act} (${frameworkLabel(frameworkKey)})`
  if (FRAMEWORK_META[frameworkKey]) return frameworkLabel(frameworkKey)
  return cleanTitle || frameworkKey.replace(/_/g, ' ') || 'Fonte'
}

/** Resolve the framework key of a citation, falling back to its CELEX. */
export function frameworkOf(c: ChiediCitation): string {
  const fromField = normalizeFramework(c.framework)
  if (fromField && (ACT_BY_FRAMEWORK[fromField] || FRAMEWORK_META[fromField])) return fromField
  if (isCelex(c.celex) && FRAMEWORK_BY_CELEX[c.celex.trim()]) return FRAMEWORK_BY_CELEX[c.celex.trim()]
  const fromTitle = normalizeFramework(c.title)
  if (fromTitle && (ACT_BY_FRAMEWORK[fromTitle] || FRAMEWORK_META[fromTitle])) return fromTitle
  return fromField || fromTitle
}

/**
 * Map one citation to the `Source` the interface shows. `index` is 1-based
 * and doubles as the in-text marker; `idPrefix` keeps ids unique when the
 * same sources are rendered in the margin and under the answer.
 */
export function citationToSource(c: ChiediCitation, index: number, idPrefix: string): Source {
  const key = frameworkOf(c)
  const known = ACT_BY_FRAMEWORK[key]
  const celex = isCelex(c.celex) ? c.celex.trim() : known?.celex
  const url = isUsefulUrl(c.url) ? c.url : celex ? eurlexUrl(celex) : undefined
  const quote = (c.quote_snippet ?? '').trim()
  const article = (c.article ?? c.reference ?? '').trim()
  return {
    id: `${idPrefix}-${index}`,
    index,
    act: actLabel(key, c.title),
    article: article || undefined,
    celex,
    url,
    quote: quote || undefined,
    status: c.verified === true ? 'verified' : 'unverified',
    origin: originOf(url),
  }
}

export function citationsToSources(citations: ChiediCitation[], idPrefix: string): Source[] {
  return citations.map((c, i) => citationToSource(c, i + 1, idPrefix))
}

/**
 * An SSE `citation` event (src/api/streaming/sse.py) as a citation. The
 * backend fills `celex` with the article reference and `title` with the
 * framework key when the agent gave nothing better, so each field is
 * checked before it is trusted. The event carries no quoted passage.
 */
export function sseCitationToChiedi(ev: CitationEvent): ChiediCitation {
  const celex = isCelex(ev.celex) ? ev.celex.trim() : undefined
  const titleKey = normalizeFramework(ev.title)
  const framework = ACT_BY_FRAMEWORK[titleKey] || FRAMEWORK_META[titleKey] ? titleKey : celex ? (FRAMEWORK_BY_CELEX[celex] ?? '') : ''
  const article = (ev.article ?? '').trim()
  return {
    framework,
    reference: article || (!celex && ev.celex ? ev.celex.trim() : ''),
    quote_snippet: '',
    article: article || undefined,
    celex,
    url: isUsefulUrl(ev.url) ? ev.url : undefined,
    title: ev.title && normalizeFramework(ev.title) !== framework ? ev.title : undefined,
    verified: ev.verified === true,
  }
}
