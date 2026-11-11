/**
 * The legal sources the Ambito rules and the deadlines calendar rely on,
 * and what the last check against the official texts found.
 *
 * - sources.json is the registry: one entry per provision, with the act
 *   (CELEX for EU acts, URN:NIR for Italian acts), the article, the
 *   paragraph and a literal excerpt of the official text that carries the
 *   date, the threshold or the duty.
 * - sources.verified.json is written by scripts/verify_site_sources.py,
 *   which reads each official text and checks the excerpt word for word.
 *
 * A source is "verified" here only when that file says so, and it carries
 * the date of that check: nothing in this module can make one up.
 */
import type { Language } from '@/i18n/config'
import registry from './sources.json'
import outcomes from './sources.verified.json'

export type SourceKind = 'eurlex' | 'normattiva' | 'document'
export type VerificationStatus = 'verified' | 'failed' | 'unreachable'

export interface LegalSource {
  id: string
  kind: SourceKind
  /** CELEX number, URN:NIR, or the identifier of an authority's document. */
  act: string
  article: string
  paragraph: string
  /** Language of the official text the excerpt was taken from. */
  lang: string
  /** How the provision is cited, in the two languages of the interface. */
  label: Record<Language, string>
  excerpt: string
  /** Number of the annex, for an annex of an Italian act. */
  annex?: number
  /** Official address, for a document of an authority. */
  url?: string
  /** Date the article is in force from, when a rule or the calendar states it (Italian acts). */
  in_force_from?: string
}

export interface VerificationRecord {
  id: string
  status: VerificationStatus
  /** ISO date of the check that found the excerpt; null unless verified. */
  verified_on: string | null
  checked_on: string
  /** What was read: a CELEX version, "vigente al <date>", or the digest of a document. */
  version: string | null
  version_label: string | null
  /** ISO date of the consolidated EU text that was read. */
  consolidated_as_of: string | null
  /** ISO date the article is in force from, as Normattiva states it. */
  in_force_from: string | null
  /** The official wording that matched the excerpt. */
  official_quote: string | null
  url: string | null
  detail: string | null
  fingerprint: string
}

interface ActName extends Record<Language, string> {
  /** Who publishes the text, when it is neither EUR-Lex nor Normattiva. */
  origin?: string
}

const SOURCES = registry.sources as LegalSource[]
const ACTS = registry.acts as Record<string, ActName>
const RECORDS = outcomes.sources as VerificationRecord[]

const SOURCE_BY_ID = new Map(SOURCES.map((s) => [s.id, s]))
const RECORD_BY_ID = new Map(RECORDS.map((r) => [r.id, r]))

/** Every id of the registry, in its order. */
export const LEGAL_SOURCE_IDS: string[] = SOURCES.map((s) => s.id)

/** The day scripts/verify_site_sources.py last wrote its outcomes. */
export const LAST_CHECK_ON: string = outcomes.generated_on

export function hasLegalSource(id: string): boolean {
  return SOURCE_BY_ID.has(id)
}

/** The registry entry of an id; an unknown id is a programming error and throws. */
export function legalSource(id: string): LegalSource {
  const source = SOURCE_BY_ID.get(id)
  if (!source) throw new Error(`Unknown legal source: ${id}`)
  return source
}

/** What the last check found for an id; undefined when the id was never checked. */
export function verificationOf(id: string): VerificationRecord | undefined {
  return RECORD_BY_ID.get(id)
}

/** ISO date of the check that verified a source, or undefined when it is not verified. */
export function verifiedOn(id: string): string | undefined {
  const record = RECORD_BY_ID.get(id)
  return record?.status === 'verified' && record.verified_on ? record.verified_on : undefined
}

/** The act as it is cited in a language; the identifier itself when the registry has no name. */
export function actName(act: string, language: Language): string {
  return ACTS[act]?.[language] ?? act
}

/** "EUR-Lex", "Normattiva" or the authority that publishes the document. */
export function originOf(source: LegalSource): string | undefined {
  if (source.kind === 'eurlex') return 'EUR-Lex'
  if (source.kind === 'normattiva') return 'Normattiva'
  return ACTS[source.act]?.origin
}

/** The most recent verification date among some sources; undefined when none is verified. */
export function latestVerifiedOn(ids: Iterable<string>): string | undefined {
  let latest: string | undefined
  for (const id of ids) {
    const date = verifiedOn(id)
    if (date && (!latest || date > latest)) latest = date
  }
  return latest
}
