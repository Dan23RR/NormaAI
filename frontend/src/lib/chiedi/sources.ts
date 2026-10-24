import { FRAMEWORK_META, frameworkLabel } from '@/components/ui/Badge'
import { eurlexLang } from '@/i18n/config'
import type { TextContext, Translate } from '@/i18n/types'
import { eurlexUrl, type Source } from '@/lib/sources'
import type { CitationEvent } from '@/hooks/useSSEStream'
import type { ChiediCitation } from './types'

/**
 * The CELEX number of the act behind each framework NormaAI covers. The
 * official name of the act, in the language of the interface, lives in the
 * `ui.acts` messages. Used to name the act and to build the EUR-Lex link
 * when the citation itself does not carry them.
 */
export const CELEX_BY_FRAMEWORK: Record<string, string> = {
  CSRD: '32022L2464',
  CSDDD: '32024L1760',
  AI_ACT: '32024R1689',
  DORA: '32022R2554',
  NIS2: '32022L2555',
  TAXONOMY: '32020R0852',
  GDPR: '32016R0679',
  CRA: '32024R2847',
  ESRS: '32023R2772',
}

const FRAMEWORK_BY_CELEX: Record<string, string> = Object.fromEntries(
  Object.entries(CELEX_BY_FRAMEWORK).map(([key, celex]) => [celex, key]),
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
export function actLabel(frameworkKey: string, title: string | undefined, t: Translate): string {
  const cleanTitle = (title ?? '').trim()
  if (cleanTitle && normalizeFramework(cleanTitle) !== frameworkKey) return cleanTitle
  if (CELEX_BY_FRAMEWORK[frameworkKey]) return `${t(`ui.acts.${frameworkKey}`)} (${frameworkLabel(frameworkKey, t)})`
  if (FRAMEWORK_META[frameworkKey]) return frameworkLabel(frameworkKey, t)
  return cleanTitle || frameworkKey.replace(/_/g, ' ') || t('ui.source')
}

/**
 * The act a CELEX number names, built from the number itself: from 2015 on,
 * 32026R1744 -> "Regulation (EU) 2026/1744"; directives of 2010-2014 used
 * the year/number/EU form, 32013L0034 -> "Directive 2013/34/EU". Older
 * regulations were numbered the other way round, so for those (and anything
 * else) the CELEX is shown as is.
 */
export function actNameFromCelex(celex: string, t: Translate): string {
  const m = /^3(\d{4})([RL])(\d{4})$/.exec(celex.trim())
  if (!m) return `${t('ui.celex')} ${celex}`
  const year = Number(m[1])
  const number = String(Number(m[3]))
  if (year >= 2015) {
    return t(m[2] === 'R' ? 'ui.actRegulation' : 'ui.actDirective', { year: m[1], number })
  }
  if (m[2] === 'L' && year >= 2010) return t('ui.actDirectiveLegacy', { year: m[1], number })
  return `${t('ui.celex')} ${celex}`
}

/** Resolve the framework key of a citation, falling back to its CELEX. */
export function frameworkOf(c: ChiediCitation): string {
  // A verified passage may sit in another act than the one cited (level "any"):
  // the verifier's CELEX is where it really is, so it wins over the model.
  if (c.verified === true && isCelex(c.celex) && FRAMEWORK_BY_CELEX[c.celex.trim()]) {
    return FRAMEWORK_BY_CELEX[c.celex.trim()]
  }
  const fromField = normalizeFramework(c.framework)
  if (fromField && (CELEX_BY_FRAMEWORK[fromField] || FRAMEWORK_META[fromField])) return fromField
  if (isCelex(c.celex) && FRAMEWORK_BY_CELEX[c.celex.trim()]) return FRAMEWORK_BY_CELEX[c.celex.trim()]
  const fromTitle = normalizeFramework(c.title)
  if (fromTitle && (CELEX_BY_FRAMEWORK[fromTitle] || FRAMEWORK_META[fromTitle])) return fromTitle
  return fromField || fromTitle
}

/**
 * Map one citation to the `Source` the interface shows. `index` is 1-based
 * and doubles as the in-text marker; `idPrefix` keeps ids unique when the
 * same sources are rendered in the margin and under the answer.
 */
export function citationToSource(c: ChiediCitation, index: number, idPrefix: string, ctx: TextContext): Source {
  const key = frameworkOf(c)
  const verified = c.verified === true
  const ownCelex = isCelex(c.celex) ? c.celex.trim() : undefined
  const celex = ownCelex ?? CELEX_BY_FRAMEWORK[key]
  const url = isUsefulUrl(c.url) ? c.url : celex ? eurlexUrl(celex, eurlexLang(ctx.locale)) : undefined
  // Verified: show the official wording, never the model's paraphrase.
  const quote = ((verified && c.official_quote) || c.quote_snippet || '').trim()
  const baseArticle = ((verified && c.article) || c.reference || c.article || '').trim()
  const paragraph = verified && c.paragraph ? String(c.paragraph).trim() : ''
  const article =
    paragraph && !/par/i.test(baseArticle) ? `${baseArticle}, ${ctx.t('ui.paragraphShort')} ${paragraph}` : baseArticle
  // An act outside the framework table (a delegated act, an amending act) is named from its CELEX.
  const act =
    verified && ownCelex && !FRAMEWORK_BY_CELEX[ownCelex] ? actNameFromCelex(ownCelex, ctx.t) : actLabel(key, c.title, ctx.t)
  return {
    id: `${idPrefix}-${index}`,
    index,
    act,
    article: article || undefined,
    celex,
    url,
    quote: quote || undefined,
    status: verified ? 'verified' : 'unverified',
    origin: originOf(url),
  }
}

export function citationsToSources(citations: ChiediCitation[], idPrefix: string, ctx: TextContext): Source[] {
  return citations.map((c, i) => citationToSource(c, i + 1, idPrefix, ctx))
}

/**
 * An SSE `citation` event (src/api/streaming/sse.py) as a citation. Older
 * backends fill `celex` with the article reference and `title` with the
 * framework key, so each field is checked before it is trusted. `quote` is
 * the official passage when the citation is verified, the model's otherwise.
 */
export function sseCitationToChiedi(ev: CitationEvent): ChiediCitation {
  const celex = isCelex(ev.celex) ? ev.celex.trim() : undefined
  const verified = ev.verified === true
  const fieldKey = normalizeFramework(ev.framework)
  const titleKey = normalizeFramework(ev.title)
  const known = (k: string) => Boolean(k && (CELEX_BY_FRAMEWORK[k] || FRAMEWORK_META[k]))
  const framework = known(fieldKey) ? fieldKey : known(titleKey) ? titleKey : celex ? (FRAMEWORK_BY_CELEX[celex] ?? '') : ''
  const article = (ev.article ?? '').trim()
  const quote = (ev.quote ?? '').trim()
  return {
    framework,
    reference: article || (!celex && ev.celex ? ev.celex.trim() : ''),
    quote_snippet: verified ? '' : quote,
    official_quote: verified && quote ? quote : undefined,
    article: article || undefined,
    paragraph: ev.paragraph,
    celex,
    url: isUsefulUrl(ev.url) ? ev.url : undefined,
    title: ev.title && normalizeFramework(ev.title) !== framework ? ev.title : undefined,
    verified,
    match: ev.match,
    level: ev.level,
    lang: ev.lang,
  }
}
