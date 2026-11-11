/**
 * The document check as the API returns it (prefix /api/v1/documents).
 *
 * A check is what stays of a document after it was read: the references it
 * makes to the law, what happened when each was compared with the official
 * text, and the provisions it depends on. The file itself is not stored.
 */

/** What to do with a finding, worst first. */
export const GROUPS = ['correggere', 'controllare', 'a_posto', 'non_coperto'] as const
export type FindingGroup = (typeof GROUPS)[number]

export function isGroup(value: unknown): value is FindingGroup {
  return typeof value === 'string' && (GROUPS as readonly string[]).includes(value)
}

/**
 * The outcome of one reference. The codes the check produces today
 * (src/document_check/check.py) have words of their own in the `controlla.status`
 * messages; a code the interface does not know is shown with the server's label.
 */
export interface FindingStatus {
  code: string
  label: string
}

export interface FindingAct {
  /** Where the official text comes from: "eurlex" or "normattiva". */
  source: string
  /** CELEX of an EU act, or the identifier of an Italian one. */
  id: string
  /** The short name: "GDPR", "AI Act". */
  name: string
  /** The act as the document writes it: "regolamento (UE) 2016/679". */
  label: string
}

export interface FindingProvision {
  /** "art:33", "recital:47", "annex:III" */
  key: string
  /** "art. 33, par. 1" */
  label: string
}

export interface FindingVersion {
  /** "02016R0679-20160504", or the CELEX of the act as adopted. */
  id: string
  /** ISO date of the consolidated text; null for the act as adopted. */
  as_of: string | null
  label: string
}

/** Words of a quote that differ from the official wording it almost matched. */
export interface Difference {
  /** The words in the document (empty when the document lacks them). */
  quoted: string
  /** The words in the official text (empty when it has none). */
  official: string
}

export interface FormerText {
  version_label: string
  text: string
}

export interface Finding {
  id: string
  group: FindingGroup
  status: FindingStatus
  /** 1-based line of the document. */
  line: number
  /** The reference as written: "articolo 33, paragrafo 1, del regolamento (UE) 2016/679". */
  raw: string
  /** A short stretch of the document around the reference. */
  context: string
  act: FindingAct | null
  provision: FindingProvision | null
  /** The version in force that the reference was checked against. */
  version: FindingVersion | null
  /** The official text on EUR-Lex or Normattiva. */
  url: string | null
  /** What the check found, in sentences. */
  messages: string[]
  /** The words the document puts in quotation marks next to the reference. */
  quotes: string[]
  /** The official wording a quote matched, or almost matched. */
  official_quote: string | null
  differences: Difference[]
  /** The provision in an earlier version, when the quote or the document rests on it. */
  before: FormerText | null
  /** The provision in force, shown next to `before`. */
  after_text: string | null
}

export const DEPENDENCY_STATES = ['current', 'changed', 'removed', 'unavailable'] as const
export type DependencyState = (typeof DEPENDENCY_STATES)[number]

/** A provision the document depends on, with what the last re-check found. */
export interface Dependency {
  source: string
  /** CELEX of the act, or URN:NIR for Italian law. */
  act: string
  name: string
  /** "Art. 33" */
  article: string
  key: string
  /** The version the document was checked against. */
  version: string
  as_of: string | null
  fingerprint: string
  state: DependencyState
  /** When a re-check found the provision changed or removed. */
  changed_at: string | null
}

export type CheckCounts = Record<FindingGroup, number>

/** A check in the list: everything but its findings and dependencies. */
export interface CheckSummary {
  id: string
  client_id: string | null
  filename: string
  document_sha256: string
  /** The date the document bears, when the person gave one (ISO). */
  document_date: string | null
  /** When the document was checked (ISO timestamp). */
  checked_at: string
  /** Language of the document: "IT" or "EN". */
  lang: string
  /** Whether the provisions it cites are re-checked on a schedule. */
  watch: boolean
  /** The worst group among the findings. */
  status: FindingGroup
  /** True when a re-check found that a cited provision changed. */
  needs_review: boolean
  counts: CheckCounts
}

export interface DocumentCheck extends CheckSummary {
  findings: Finding[]
  dependencies: Dependency[]
}

export interface CheckList {
  items: CheckSummary[]
  total: number
}

export interface DocumentPreferences {
  /** Whether the email digest is sent after a re-check that found changes. */
  email_digest: boolean
}

/** The findings of a group, in the order of the document. */
export function findingsOf(check: Pick<DocumentCheck, 'findings'>, group: FindingGroup): Finding[] {
  return check.findings.filter((f) => f.group === group)
}

/** The dependency a finding rests on, when the check recorded one. */
export function dependencyOf(check: Pick<DocumentCheck, 'dependencies'>, finding: Finding): Dependency | undefined {
  if (!finding.act || !finding.provision) return undefined
  return check.dependencies.find((d) => d.act === finding.act?.id && d.key === finding.provision?.key)
}

/** True when a re-check found the provision changed or gone after the document was checked. */
export function isStale(dependency: Dependency | undefined): boolean {
  return dependency?.state === 'changed' || dependency?.state === 'removed'
}
