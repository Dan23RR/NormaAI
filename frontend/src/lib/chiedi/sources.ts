import { FRAMEWORK_META, frameworkLabel } from '@/components/ui/Badge'
import { eurlexLang } from '@/i18n/config'
import type { TextContext, Translate } from '@/i18n/types'
import { eurlexUrl, type Source } from '@/lib/sources'
import type { CitationEvent } from '@/hooks/useSSEStream'
import type { ChiediCitation, CitationDifference } from './types'

/**
 * A quote that is not in the official text as written, next to the official
 * wording it almost matched: what the answer says, what the law says, where,
 * and the words that differ.
 */
export interface NearMatch {
  /** The words as the answer quotes them. */
  quoted: string
  /** The official wording. */
  official: string
  /** Where the official wording is, e.g. "Art. 33". */
  article?: string
  differences: CitationDifference[]
}

/**
 * A quote found word for word in the official text, but not where the citation
 * points: in another act, in another article of the act cited or in another
 * paragraph of the article cited. Never a verified source.
 */
export interface Elsewhere {
  where: 'act' | 'article' | 'paragraph'
  /** Where the wording is, e.g. "Regolamento (UE) 2024/1689 (AI Act), Art. 50". */
  location: string
  /** The official wording found there. */
  quote?: string
  /** EUR-Lex link to the act where it is. */
  url?: string
}

/**
 * A source of the Chiedi margin: the shared `Source`, plus the near match of an
 * unverified quote or the place where a quote found elsewhere really is.
 */
export interface ChiediSource extends Source {
  near?: NearMatch
  elsewhere?: Elsewhere
}

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

/** The act a CELEX number names: from the framework table when it is there, else from the number. */
export function actOfCelex(celex: string, t: Translate): string {
  const key = FRAMEWORK_BY_CELEX[celex.trim()]
  return key ? actLabel(key, undefined, t) : actNameFromCelex(celex, t)
}

/**
 * A bracketed reference of the answer as the reader sees it. The backend labels
 * an act other than the main one of its framework with its CELEX (the Digital
 * Omnibus on AI is no article of the AI Act): "[32026R1744, Art. 1]" reads
 * "[Regolamento (UE) 2026/1744, Art. 1]". Any other label is left as it is.
 */
export function markerLabel(label: string, t: Translate): string {
  const comma = label.indexOf(',')
  const head = (comma >= 0 ? label.slice(0, comma) : label).trim()
  if (!isCelex(head)) return label
  const rest = comma >= 0 ? label.slice(comma + 1).trim() : ''
  return rest ? `${actOfCelex(head, t)}, ${rest}` : actOfCelex(head, t)
}

/** The answer text with every bracketed CELEX reference named as markerLabel does. */
export function withActNames(text: string, t: Translate): string {
  return text.replace(/\[([^[\]\n]+)\]/g, (all, inner: string) => {
    const shown = markerLabel(inner, t)
    return shown === inner ? all : `[${shown}]`
  })
}

interface FoundElsewhere {
  where: Elsewhere['where']
  celex?: string | null
  article?: string | null
  paragraph?: string | null
  quote?: string | null
  url?: string | null
}

const FOUND_IN: ReadonlyArray<Elsewhere['where']> = ['act', 'article', 'paragraph']

/** The number an article reference names, with its letter: "Art. 19a(1)" -> "19a". */
function articleNumber(ref: string | null | undefined): string {
  const m = /(\d{1,4})\s*([a-z])?(?![a-z])/i.exec(ref ?? '')
  return m ? `${m[1]}${(m[2] ?? '').toLowerCase()}` : ''
}

/**
 * Where the wording of a citation really is, when that is not where the citation
 * points: the verifier's `found_*` fields. An answer kept from before the backend
 * reported them carries the old form, a passage "verified" in another act
 * (`level: 'any'`) or in another article of the act (`level: 'framework'`):
 * it is read the same way.
 */
function foundElsewhere(c: ChiediCitation): FoundElsewhere | undefined {
  if (c.found_elsewhere === true) {
    const where = c.found_in && FOUND_IN.includes(c.found_in) ? c.found_in : 'act'
    return {
      where,
      celex: c.found_celex,
      article: c.found_article,
      paragraph: c.found_paragraph,
      quote: c.found_quote,
      url: c.found_url,
    }
  }
  if (c.verified !== true) return undefined
  const legacy = { celex: c.celex, article: c.article, paragraph: c.paragraph, quote: c.official_quote, url: c.url }
  if (c.level === 'any') return { where: 'act', ...legacy }
  if (c.level === 'framework') {
    const cited = articleNumber(c.reference)
    const found = articleNumber(c.article)
    if (cited && found && cited !== found) return { where: 'article', ...legacy }
  }
  return undefined
}

/** The place where a quote found elsewhere really is, as the margin shows it. */
export function elsewhereOf(c: ChiediCitation, ctx: TextContext): Elsewhere | undefined {
  const found = foundElsewhere(c)
  if (!found) return undefined
  const celex = isCelex(found.celex) ? found.celex.trim() : undefined
  const article = (found.article ?? '').trim()
  const paragraph = String(found.paragraph ?? '').trim()
  const place = article && paragraph ? `${article}, ${ctx.t('ui.paragraphShort')} ${paragraph}` : article
  const parts = found.where === 'act' && celex ? [actOfCelex(celex, ctx.t)] : []
  if (place) parts.push(place)
  const quote = (found.quote ?? '').trim()
  return {
    where: found.where,
    location: parts.join(', ') || ctx.t('ui.source'),
    quote: quote || undefined,
    url: isUsefulUrl(found.url) ? found.url : celex ? eurlexUrl(celex, eurlexLang(ctx.locale)) : undefined,
  }
}

/** Resolve the framework key of a citation, falling back to its CELEX. */
export function frameworkOf(c: ChiediCitation): string {
  // The backend verifies a citation only in the act it cites, so a verified
  // CELEX names that act and wins over the model's label. A quote found in
  // another act keeps the label the answer gives it.
  if (c.verified === true && !foundElsewhere(c) && isCelex(c.celex) && FRAMEWORK_BY_CELEX[c.celex.trim()]) {
    return FRAMEWORK_BY_CELEX[c.celex.trim()]
  }
  const fromField = normalizeFramework(c.framework)
  if (fromField && (CELEX_BY_FRAMEWORK[fromField] || FRAMEWORK_META[fromField])) return fromField
  // An act cited by its CELEX: the framework key when it is a main act, else the CELEX itself.
  if (isCelex(fromField)) return FRAMEWORK_BY_CELEX[fromField] ?? fromField
  if (isCelex(c.celex) && FRAMEWORK_BY_CELEX[c.celex.trim()]) return FRAMEWORK_BY_CELEX[c.celex.trim()]
  const fromTitle = normalizeFramework(c.title)
  if (fromTitle && (CELEX_BY_FRAMEWORK[fromTitle] || FRAMEWORK_META[fromTitle])) return fromTitle
  return fromField || fromTitle
}

function asDifferences(value: unknown): CitationDifference[] {
  if (!Array.isArray(value)) return []
  return value
    .filter((d): d is Record<string, unknown> => !!d && typeof d === 'object')
    .map((d) => ({
      quoted: typeof d.quoted === 'string' ? d.quoted.trim() : '',
      official: typeof d.official === 'string' ? d.official.trim() : '',
    }))
    .filter((d) => d.quoted || d.official)
}

/**
 * The near match of a citation: only for a quote that is NOT verified and for
 * which the verifier found the official wording it differs from. A verified
 * citation never has one, whatever fields it carries.
 */
export function nearMatchOf(c: ChiediCitation): NearMatch | undefined {
  if (c.verified === true) return undefined
  const official = typeof c.near_quote === 'string' ? c.near_quote.trim() : ''
  if (!official) return undefined
  const article = typeof c.near_article === 'string' ? c.near_article.trim() : ''
  return {
    quoted: (c.quote_snippet ?? '').trim(),
    official,
    article: article || undefined,
    differences: asDifferences(c.differences),
  }
}

/**
 * Map one citation to the `Source` the interface shows. `index` is 1-based
 * and doubles as the in-text marker; `idPrefix` keeps ids unique when the
 * same sources are rendered in the margin and under the answer.
 */
export function citationToSource(c: ChiediCitation, index: number, idPrefix: string, ctx: TextContext): ChiediSource {
  const key = frameworkOf(c)
  const elsewhere = elsewhereOf(c, ctx)
  // Found in another act, article or paragraph: never verified, whatever the flag says.
  const verified = c.verified === true && !elsewhere
  // The CELEX and link of a quote found elsewhere are those of the place it was found:
  // they go with `elsewhere`, and the source names the act the answer cites.
  const ownCelex = !elsewhere && isCelex(c.celex) ? c.celex.trim() : undefined
  const celex = ownCelex ?? (isCelex(key) ? key : CELEX_BY_FRAMEWORK[key])
  const url = !elsewhere && isUsefulUrl(c.url) ? c.url : celex ? eurlexUrl(celex, eurlexLang(ctx.locale)) : undefined
  const near = nearMatchOf(c)
  // Verified: show the official wording, never the model's paraphrase. A quote known to
  // differ from the official text is not shown as the passage of law: it goes with `near`,
  // and the wording of a quote found elsewhere goes with `elsewhere`.
  const quote = near || elsewhere ? '' : ((verified && c.official_quote) || c.quote_snippet || '').trim()
  const baseArticle = ((verified && c.article) || c.reference || c.article || '').trim()
  const paragraph = verified && c.paragraph ? String(c.paragraph).trim() : ''
  const article =
    paragraph && !/par/i.test(baseArticle) ? `${baseArticle}, ${ctx.t('ui.paragraphShort')} ${paragraph}` : baseArticle
  // An act outside the framework table (a delegated act, an amending act) is named from its CELEX,
  // also when the citation names it by its CELEX, as the backend labels it.
  const act =
    verified && ownCelex && !FRAMEWORK_BY_CELEX[ownCelex]
      ? actNameFromCelex(ownCelex, ctx.t)
      : isCelex(key)
        ? actOfCelex(key, ctx.t)
        : actLabel(key, c.title, ctx.t)
  // An article verified in the text of the act that amends it: say so (the link goes there).
  const note =
    verified && isCelex(c.amending_celex)
      ? ctx.t('ui.quotedIn', { act: actOfCelex(c.amending_celex, ctx.t), article: (c.amending_article ?? '').trim() })
      : undefined
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
    note,
    near,
    elsewhere,
  }
}

export function citationsToSources(citations: ChiediCitation[], idPrefix: string, ctx: TextContext): ChiediSource[] {
  return citations.map((c, i) => citationToSource(c, i + 1, idPrefix, ctx))
}

/**
 * An SSE `citation` event (src/api/streaming/sse.py) as a citation. Older
 * backends fill `celex` with the article reference and `title` with the
 * framework key, so each field is checked before it is trusted. `quote` is
 * the official passage when the citation is verified, the model's otherwise.
 * The near match (`near_quote`, `near_article`, `differences`) is kept only
 * for a citation that is not verified.
 */
export function sseCitationToChiedi(ev: CitationEvent): ChiediCitation {
  const celex = isCelex(ev.celex) ? ev.celex.trim() : undefined
  const verified = ev.verified === true
  const fieldKey = normalizeFramework(ev.framework)
  const titleKey = normalizeFramework(ev.title)
  const known = (k: string) => Boolean(k && (CELEX_BY_FRAMEWORK[k] || FRAMEWORK_META[k]))
  // A framework given as a CELEX (an act other than the main one of its framework) is kept.
  const framework = known(fieldKey) || isCelex(fieldKey)
    ? fieldKey
    : known(titleKey)
      ? titleKey
      : celex
        ? (FRAMEWORK_BY_CELEX[celex] ?? '')
        : ''
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
    amending_celex: verified && isCelex(ev.amending_celex) ? ev.amending_celex.trim() : undefined,
    amending_article: verified ? ev.amending_article : undefined,
    near_quote: !verified && typeof ev.near_quote === 'string' && ev.near_quote.trim() ? ev.near_quote.trim() : undefined,
    near_article: !verified && typeof ev.near_article === 'string' && ev.near_article.trim() ? ev.near_article.trim() : undefined,
    differences: !verified && Array.isArray(ev.differences) ? asDifferences(ev.differences) : undefined,
    ...(!verified && ev.found_elsewhere === true
      ? {
          found_elsewhere: true,
          found_in: ev.found_in,
          found_celex: isCelex(ev.found_celex) ? ev.found_celex.trim() : undefined,
          found_article: ev.found_article,
          found_paragraph: ev.found_paragraph,
          found_quote: ev.found_quote,
          found_url: isUsefulUrl(ev.found_url) ? ev.found_url : undefined,
        }
      : {}),
  }
}
