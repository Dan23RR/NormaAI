/**
 * The legal sources of the scope engine and of the obligations calendar,
 * as the interface shows them. Each one is an entry of the registry in
 * src/lib/verification: its status and its date come from the last run of
 * scripts/verify_site_sources.py, never from this module. A source that
 * check did not find is shown as "not yet verified", without a quote.
 * Nothing here is a legal opinion.
 */
import { eurlexLang, languageOf } from '@/i18n/config'
import { formatDate } from '@/i18n/format'
import type { TextContext } from '@/i18n/types'
import { eurlexUrl, type Source } from '@/lib/sources'
import { actName, legalSource, originOf, verificationOf, type SourceKind } from '@/lib/verification'

/** A registry source ready for display. */
export interface ScopeSource extends Source {
  kind: SourceKind
  /** ISO date of the consolidated EU text the passage was found in. */
  textAsOf?: string
  /** Language of the quoted passage (BCP 47). */
  quoteLang?: string
}

const CELEX_VERSION = /^\d{5}[A-Z]\d{4}(-\d{8})?$/

/** One line of official text: the breaks of the source page are not part of the wording. */
function oneLine(text: string): string {
  return text.replace(/\s+/g, ' ').trim()
}

function linkOf(id: string, ctx: TextContext): string | undefined {
  const source = legalSource(id)
  const record = verificationOf(id)
  if (source.kind === 'eurlex') {
    // The page of the version that was read, in the language of the interface.
    const version = record?.version && CELEX_VERSION.test(record.version) ? record.version : source.act
    return eurlexUrl(version, eurlexLang(ctx.locale))
  }
  if (source.kind === 'normattiva') return record?.url ?? `https://www.normattiva.it/uri-res/N2Ls?${source.act}`
  return source.url
}

/** The source of a registry id in the words of the interface; an unknown id throws. */
export function scopeSource(id: string, ctx: TextContext): ScopeSource {
  const source = legalSource(id)
  const record = verificationOf(id)
  const verified = record?.status === 'verified' && Boolean(record.verified_on)
  const language = languageOf(ctx.locale)
  return {
    id,
    index: 0,
    kind: source.kind,
    act: actName(source.act, language),
    article: source.label[language],
    celex: source.kind === 'eurlex' ? source.act : undefined,
    url: linkOf(id, ctx),
    origin: originOf(source),
    status: verified ? 'verified' : 'unverified',
    verifiedAt: verified ? (record?.verified_on ?? undefined) : undefined,
    quote: verified && record?.official_quote ? oneLine(record.official_quote) : undefined,
    quoteLang: source.lang.toLowerCase(),
    textAsOf: verified ? (record?.consolidated_as_of ?? undefined) : undefined,
  }
}

/** The sources of some registry ids, numbered 1..n, without duplicates. */
export function scopeSources(ids: string[], ctx: TextContext): ScopeSource[] {
  return withIndex(ids.map((id) => scopeSource(id, ctx)))
}

/** Returns the sources renumbered 1..n, without duplicates, ready for display. */
export function withIndex<T extends Source>(sources: T[]): T[] {
  const seen = new Set<string>()
  const unique = sources.filter((s) => {
    if (seen.has(s.id)) return false
    seen.add(s.id)
    return true
  })
  return unique.map((s, i) => ({ ...s, index: i + 1 }))
}

/**
 * "il 2 dicembre 2026", "l’11 novembre 2026": Italian puts the article
 * before a date and elides it before 1, 8 and 11. English takes the date alone.
 */
export function dateWithArticle(iso: string, ctx: TextContext): string {
  const text = formatDate(iso, ctx)
  if (languageOf(ctx.locale) !== 'it') return text
  const day = Number(iso.slice(8, 10))
  return day === 1 || day === 8 || day === 11 ? `l’${text}` : `il ${text}`
}

/**
 * What the last check says about a source: "Verificata l’11 novembre 2026"
 * with the text it was found in, or "Fonte indicata, non ancora verificata".
 */
export function verificationLabel(source: Source, ctx: TextContext): string {
  if (source.status !== 'verified' || !source.verifiedAt) return ctx.t('ambito.verification.notVerified')
  const date = dateWithArticle(source.verifiedAt, ctx)
  const textAsOf = (source as ScopeSource).textAsOf
  if (textAsOf) {
    return ctx.t('ambito.verification.verifiedConsolidated', { date, textDate: formatDate(textAsOf, ctx) })
  }
  return ctx.t('ambito.verification.verified', { date })
}

/** "Regolamento (UE) 2024/1689 (AI Act), art. 50, par. 1 (CELEX 32024R1689) <url>. Verificata ..." */
export function sourceLine(source: Source, ctx?: TextContext): string {
  const parts = [source.act]
  if (source.article) parts.push(source.article)
  let line = parts.join(', ')
  if (source.celex) line += ` (CELEX ${source.celex})`
  if (source.url) line += ` ${source.url}`
  if (ctx) line += `. ${verificationLabel(source, ctx)}`
  return line
}
