/**
 * Word-level differences between two texts, for the two places where the
 * interface shows how a wording differs: a provision before and after an
 * amendment, and a quote next to the official wording it almost matched.
 *
 * No dependency: Myers' shortest edit script over the words. Its cost grows
 * with the number of words that differ, not with the length of the texts, so
 * a long article with a few amended words is cheap. Two texts that share
 * almost nothing stop at `MAX_EDITS` and are reported as "all of this was
 * replaced by all of that", which is also the honest way to show them.
 */

export type DiffKind = 'equal' | 'removed' | 'added' | 'omitted'

export interface DiffSegment {
  kind: DiffKind
  /** The words of the segment, joined by single spaces; empty for `omitted`. */
  text: string
  /** How many words the segment holds (`omitted`: how many unchanged words were left out). */
  count: number
}

/** A stretch of words: `a` indexes the first text, `b` the second, end excluded. */
export interface WordRun {
  kind: 'equal' | 'removed' | 'added'
  a1: number
  a2: number
  b1: number
  b2: number
}

/** Above this many differing words the two texts are shown as a full replacement. */
export const MAX_EDITS = 2000

// A number written with spaces between the thousands, as the Official Journal does
// ("1 000", "450 000 000", with what is attached to its end), or anything else up to
// the next space.
const WORD = /\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?!\d)\S*|\S+/g

/**
 * The words of a text. Line breaks count as spaces: the wording is what is
 * compared. A number with spaces between its thousands is one word, so that
 * "1 000" becoming "5 000" reads as one number replaced by another.
 */
export function splitWords(text: string): string[] {
  return text.match(WORD) ?? []
}

/**
 * A comparison key that forgives what the citation verifier forgives in a
 * quote: case, accents, typographic apostrophes and the punctuation around a
 * word. Numbers and the words themselves stay as they are.
 */
export function looseKey(word: string): string {
  return word
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[‘’`]/g, "'")
    .replace(/^[^0-9a-zß-ɏ]+|[^0-9a-zß-ɏ]+$/g, '')
}

type Edit = 'equal' | 'removed' | 'added'

/** Myers' algorithm; null when the texts differ by more than `maxEdits` words. */
function editScript(a: string[], b: string[], maxEdits: number): Edit[] | null {
  const n = a.length
  const m = b.length
  const max = Math.min(n + m, maxEdits)
  const offset = max + 1
  // v[offset + k] is the furthest x reached on diagonal k (x - y = k).
  const v = new Int32Array(2 * max + 3)
  const trace: Int32Array[] = []

  for (let d = 0; d <= max; d++) {
    // What the previous round reached, on the diagonals this round reads.
    trace.push(v.slice(offset - d - 1, offset + d + 2))
    for (let k = -d; k <= d; k += 2) {
      const down = k === -d || (k !== d && v[offset + k - 1] < v[offset + k + 1])
      let x = down ? v[offset + k + 1] : v[offset + k - 1] + 1
      let y = x - k
      while (x < n && y < m && a[x] === b[y]) {
        x++
        y++
      }
      v[offset + k] = x
      if (x >= n && y >= m) return backtrack(trace, d, n, m)
    }
  }
  return null
}

function backtrack(trace: Int32Array[], rounds: number, n: number, m: number): Edit[] {
  const edits: Edit[] = []
  let x = n
  let y = m
  for (let d = rounds; d >= 0; d--) {
    const before = trace[d]
    const at = (k: number) => before[k + d + 1]
    const k = x - y
    const down = k === -d || (k !== d && at(k - 1) < at(k + 1))
    const prevK = down ? k + 1 : k - 1
    const prevX = at(prevK)
    const prevY = prevX - prevK
    while (x > prevX && y > prevY) {
      edits.push('equal')
      x--
      y--
    }
    if (d > 0) {
      edits.push(down ? 'added' : 'removed')
      if (down) y--
      else x--
    }
  }
  return edits.reverse()
}

/**
 * The two word lists as runs of equal, removed and added words, in reading
 * order. Inside a change the removed words always come before the added
 * ones. `key` decides when two words are the same (identity by default).
 */
export function diffRuns(
  a: string[],
  b: string[],
  key: (word: string) => string = (word) => word,
  maxEdits: number = MAX_EDITS,
): WordRun[] {
  const edits = editScript(a.map(key), b.map(key), maxEdits)
  const runs: WordRun[] = []
  if (edits === null) {
    if (a.length) runs.push({ kind: 'removed', a1: 0, a2: a.length, b1: 0, b2: 0 })
    if (b.length) runs.push({ kind: 'added', a1: a.length, a2: a.length, b1: 0, b2: b.length })
    return runs
  }

  let i = 0
  let j = 0
  let at = 0
  while (at < edits.length) {
    if (edits[at] === 'equal') {
      const start = at
      while (at < edits.length && edits[at] === 'equal') at++
      const length = at - start
      runs.push({ kind: 'equal', a1: i, a2: i + length, b1: j, b2: j + length })
      i += length
      j += length
      continue
    }
    let removed = 0
    let added = 0
    while (at < edits.length && edits[at] !== 'equal') {
      if (edits[at] === 'removed') removed++
      else added++
      at++
    }
    if (removed) runs.push({ kind: 'removed', a1: i, a2: i + removed, b1: j, b2: j })
    if (added) runs.push({ kind: 'added', a1: i + removed, a2: i + removed, b1: j, b2: j + added })
    i += removed
    j += added
  }
  return runs
}

export interface DiffOptions {
  key?: (word: string) => string
  /**
   * Shorten every unchanged stretch longer than `longerThan` words to its
   * first and last `keep` words, with an `omitted` segment in between.
   */
  collapse?: { longerThan: number; keep: number }
}

/**
 * `before` and `after` as segments to print one after the other. Unchanged
 * words are taken from `after`, the text that counts today.
 */
export function diffWords(before: string, after: string, options: DiffOptions = {}): DiffSegment[] {
  const a = splitWords(before)
  const b = splitWords(after)
  const segments: DiffSegment[] = []
  for (const run of diffRuns(a, b, options.key)) {
    if (run.kind === 'removed') {
      segments.push({ kind: 'removed', text: a.slice(run.a1, run.a2).join(' '), count: run.a2 - run.a1 })
      continue
    }
    const words = b.slice(run.b1, run.b2)
    if (run.kind === 'added') {
      segments.push({ kind: 'added', text: words.join(' '), count: words.length })
      continue
    }
    const collapse = options.collapse
    if (collapse && words.length > collapse.longerThan && words.length > collapse.keep * 2) {
      segments.push({ kind: 'equal', text: words.slice(0, collapse.keep).join(' '), count: collapse.keep })
      segments.push({ kind: 'omitted', text: '', count: words.length - collapse.keep * 2 })
      segments.push({ kind: 'equal', text: words.slice(-collapse.keep).join(' '), count: collapse.keep })
    } else {
      segments.push({ kind: 'equal', text: words.join(' '), count: words.length })
    }
  }
  return segments
}

/** True when the segments hold at least one removed or added word. */
export function hasChanges(segments: DiffSegment[]): boolean {
  return segments.some((s) => s.kind === 'removed' || s.kind === 'added')
}

export interface ChangedSpan {
  before: string
  changed: string
  after: string
}

/**
 * Where the official wording differs from a quote of it: the official words
 * the quote does not have, with what stands before and after them. Null when
 * the difference is not one stretch of the official text (several places, or
 * words the quote adds), so the caller shows the whole wording instead.
 */
export function changedSpan(quoted: string, official: string): ChangedSpan | null {
  const a = splitWords(quoted)
  const b = splitWords(official)
  const runs = diffRuns(a, b, looseKey)
  const added = runs.filter((run) => run.kind === 'added')
  const removedAlone = runs.some(
    (run, index) => run.kind === 'removed' && runs[index + 1]?.kind !== 'added',
  )
  if (added.length !== 1 || removedAlone) return null
  const { b1, b2 } = added[0]
  return {
    before: b.slice(0, b1).join(' '),
    changed: b.slice(b1, b2).join(' '),
    after: b.slice(b2).join(' '),
  }
}
