import { describe, it, expect } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import itMessages from '../../../../messages/it.json'
import enMessages from '../../../../messages/en.json'
import { COOKIES, LOCAL_STORAGE, SESSION_STORAGE } from '../storage-keys'

/**
 * The cookie policy is a legal page: it must list the keys the code really
 * sets, no more and no less. This test reads the source the way the list was
 * built (a grep of the files that touch localStorage, sessionStorage or
 * document.cookie) and fails when the two drift apart.
 */

const SRC = join(__dirname, '..', '..', '..')

function sourceFiles(dir: string): string[] {
  const out: string[] = []
  for (const name of readdirSync(dir)) {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) {
      if (name === '__tests__' || name === 'test') continue
      out.push(...sourceFiles(path))
    } else if (/\.(ts|tsx)$/.test(name) && !/\.test\.tsx?$/.test(name)) {
      out.push(path)
    }
  }
  return out
}

/** `'normaai_x'`, `"normaai.x"` or `` `normaai_x_${id}` `` (the last one as `normaai_x_*`). */
const KEY_LITERAL = /['"`](normaai[._-][A-Za-z0-9._-]*)(\$\{)?/g

function keysUsedInSource(): Map<string, string[]> {
  const found = new Map<string, string[]>()
  for (const file of sourceFiles(SRC)) {
    const rel = relative(SRC, file).split(sep).join('/')
    if (rel.startsWith('app/cookie/')) continue // the policy itself
    const text = readFileSync(file, 'utf8')
    if (!/localStorage|sessionStorage|document\.cookie/.test(text)) continue
    for (const match of text.matchAll(KEY_LITERAL)) {
      const key = match[2] ? `${match[1]}*` : match[1]
      found.set(key, [...(found.get(key) ?? []), rel])
    }
  }
  return found
}

describe('cookie policy storage keys', () => {
  const documented = [...COOKIES, ...LOCAL_STORAGE, ...SESSION_STORAGE]
  const used = keysUsedInSource()

  it('lists every key the source sets or reads', () => {
    const listed = new Set(documented.map((row) => row.key))
    const missing = [...used.entries()].filter(([key]) => !listed.has(key)).map(([key, files]) => `${key} (${files[0]})`)
    expect(missing, 'keys used in src/ but missing from the cookie policy').toEqual([])
  })

  it('lists no key the source no longer uses', () => {
    const stale = documented.filter((row) => !used.has(row.key)).map((row) => row.key)
    expect(stale, 'keys in the cookie policy that no source file uses').toEqual([])
  })

  it('finds the key of every storage call, so that none escapes the grep above', () => {
    // A call whose key is neither a "normaai…" literal nor a constant holding one
    // would set a key the two tests above cannot see.
    const files = sourceFiles(SRC).map((file) => readFileSync(file, 'utf8'))
    const all = files.join('\n')
    const holdsKey = (name: string) =>
      new RegExp(`\\b(?:const|let)\\s+${name}\\s*=\\s*(?:\\([^)]*\\)\\s*=>\\s*)?['"\`]normaai[._-]`).test(all)
    const unknown: string[] = []
    for (const text of files) {
      for (const call of text.matchAll(/(?:localStorage|sessionStorage)\.(?:getItem|setItem|removeItem)\(\s*([^,)]+)/g)) {
        const arg = call[1].trim()
        if (/^['"`]normaai[._-]/.test(arg)) continue
        const name = arg.match(/^([A-Za-z_$][\w$]*)/)?.[1]
        if (!name || !holdsKey(name)) unknown.push(arg)
      }
    }
    expect(unknown, 'storage calls whose key the cookie policy cannot list').toEqual([])
  })

  it('lists each key once, with its words in both languages', () => {
    expect(new Set(documented.map((row) => row.key)).size).toBe(documented.length)
    expect(new Set(documented.map((row) => row.id)).size).toBe(documented.length)
    for (const messages of [itMessages, enMessages]) {
      const rows = messages.legal.cookie.rows as Record<string, { purpose: string; duration: string }>
      expect(Object.keys(rows).sort()).toEqual(documented.map((row) => row.id).sort())
    }
  })
})
