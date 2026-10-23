import { normalizeFramework } from './sources'
import type { ChiediCitation } from './types'

/**
 * The answer text as the backend writes it: paragraphs separated by blank
 * lines, numbered or bulleted lines, `**bold**` runs and bracketed
 * references such as "[1]" or "[NIS2, Art. 23(4)(a)]". This module turns
 * it into blocks the page renders, resolving each bracket to a source
 * number when it matches one of the answer's citations.
 */

export type InlineToken =
  | { type: 'text'; text: string }
  | { type: 'strong'; text: string }
  | { type: 'marker'; label: string; index: number | null }

export type Block =
  | { type: 'paragraph'; inline: InlineToken[] }
  | { type: 'list'; ordered: boolean; items: InlineToken[][] }

export type MarkerResolver = (label: string) => number | null

const ORDERED_RE = /^(\d{1,3})[.)]\s+/
const BULLET_RE = /^[-•*]\s+/
const INLINE_RE = /\*\*([^*]+?)\*\*|\[([^[\]\n]+)\]/g

/**
 * "Art. 23(4)(a)", "art. 23, par. 4, lett. a)" and "articolo 23 paragrafo 4
 * lettera a" all become "art23,4,a", so the answer's brackets match the
 * citations whatever notation the model used.
 */
function normalizeRef(ref: string): string {
  return ref
    .toLowerCase()
    .replace(/\(([^()]+)\)/g, ',$1')
    .replace(/\b(?:articolo|article|artt?)\b\.?/g, 'art')
    .replace(/\b(?:paragrafo|paragraph|par|comma|lettera|letter|lett|punto|point)\b\.?/g, ',')
    .replace(/[^a-z0-9,]+/g, '')
    .replace(/,+/g, ',')
    .replace(/^,|,$/g, '')
}

/**
 * Build the resolver for an answer: "[3]" maps to source 3 when it exists;
 * "[GDPR, Art. 22(1)]" maps to the citation with that framework and
 * reference (exact, or unique prefix match); anything else stays text.
 */
export function resolverFor(citations: ChiediCitation[]): MarkerResolver {
  const entries = citations.map((c, i) => ({
    index: i + 1,
    framework: normalizeFramework(c.framework),
    ref: normalizeRef(c.article ?? c.reference ?? ''),
  }))

  const unique = (matches: number[]): number | null => (matches.length === 1 ? matches[0] : null)

  return (label: string) => {
    const trimmed = label.trim()
    if (/^\d{1,3}$/.test(trimmed)) {
      const n = Number(trimmed)
      return n >= 1 && n <= citations.length ? n : null
    }
    const comma = trimmed.indexOf(',')
    const fwPart = comma >= 0 ? trimmed.slice(0, comma) : ''
    const refPart = comma >= 0 ? trimmed.slice(comma + 1) : trimmed
    const fw = normalizeFramework(fwPart)
    const ref = normalizeRef(refPart)
    if (!ref) return null
    const pool = fw ? entries.filter((e) => e.framework === fw) : entries
    const exact = pool.filter((e) => e.ref === ref).map((e) => e.index)
    if (exact.length) return unique(exact)
    const prefix = pool.filter((e) => e.ref && (ref.startsWith(e.ref) || e.ref.startsWith(ref))).map((e) => e.index)
    return unique(prefix)
  }
}

export function parseInline(text: string, resolve: MarkerResolver): InlineToken[] {
  const tokens: InlineToken[] = []
  let last = 0
  const re = new RegExp(INLINE_RE.source, 'g')
  let m: RegExpExecArray | null
  while ((m = re.exec(text)) !== null) {
    const start = m.index
    if (start > last) tokens.push({ type: 'text', text: text.slice(last, start) })
    if (m[1] !== undefined) tokens.push({ type: 'strong', text: m[1] })
    else tokens.push({ type: 'marker', label: m[2], index: resolve(m[2]) })
    last = start + m[0].length
  }
  if (last < text.length) tokens.push({ type: 'text', text: text.slice(last) })
  return tokens
}

export function parseAnswer(text: string, resolve: MarkerResolver = () => null): Block[] {
  const blocks: Block[] = []
  const lines = text.replace(/\r\n?/g, '\n').split('\n')
  let list: { ordered: boolean; items: InlineToken[][] } | null = null

  const flushList = () => {
    if (list) blocks.push({ type: 'list', ordered: list.ordered, items: list.items })
    list = null
  }

  for (const raw of lines) {
    const line = raw.trim()
    if (!line) {
      flushList()
      continue
    }
    const ordered = ORDERED_RE.test(line)
    const bullet = !ordered && BULLET_RE.test(line)
    if (ordered || bullet) {
      const item = parseInline(line.replace(ordered ? ORDERED_RE : BULLET_RE, ''), resolve)
      if (list && list.ordered === ordered) list.items.push(item)
      else {
        flushList()
        list = { ordered, items: [item] }
      }
      continue
    }
    flushList()
    blocks.push({ type: 'paragraph', inline: parseInline(line, resolve) })
  }
  flushList()
  return blocks
}

/** The answer without markdown emphasis, for the clipboard. */
export function answerToPlainText(text: string): string {
  return text.replace(/\r\n?/g, '\n').replace(/\*\*([^*]+?)\*\*/g, '$1').trim()
}
