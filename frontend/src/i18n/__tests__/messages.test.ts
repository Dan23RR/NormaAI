import { describe, it, expect } from 'vitest'
// The ICU parser behind intl-messageformat, which next-intl uses at runtime.
import { parse, TYPE, type MessageFormatElement } from '@formatjs/icu-messageformat-parser'
import itMessages from '../../../messages/it.json'
import enMessages from '../../../messages/en.json'

type Tree = { [key: string]: string | Tree }

/** Every leaf path of a messages tree, e.g. "chiedi.answer.copy", with its text. */
function leaves(tree: Tree, prefix = ''): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [key, value] of Object.entries(tree)) {
    const path = prefix ? `${prefix}.${key}` : key
    if (typeof value === 'string') out[path] = value
    else Object.assign(out, leaves(value, path))
  }
  return out
}

/**
 * The ICU arguments ({name}) and rich tags (<name>) a message uses, sorted,
 * read from the parsed message (the parser next-intl itself relies on), so
 * a message that does not parse fails the test with its key.
 */
function placeholders(message: string): string[] {
  const found = new Set<string>()
  const walk = (elements: MessageFormatElement[]) => {
    for (const el of elements) {
      if (el.type === TYPE.literal || el.type === TYPE.pound) continue
      if (el.type === TYPE.tag) {
        found.add(`<${el.value}>`)
        walk(el.children)
        continue
      }
      found.add(`{${el.value}}`)
      if (el.type === TYPE.select || el.type === TYPE.plural) {
        for (const option of Object.values(el.options)) walk(option.value)
      }
    }
  }
  walk(parse(message))
  return Array.from(found).sort()
}

const NAMESPACES = [
  'site',
  'landing',
  'login',
  'app',
  'chiedi',
  'ambito',
  'monitoraggio',
  'clienti',
  'report',
  'impostazioni',
  'admin',
  'legal',
  'ui',
  'errors',
]

describe('messages', () => {
  const itLeaves = leaves(itMessages as Tree)
  const enLeaves = leaves(enMessages as Tree)
  const itKeys = Object.keys(itLeaves)
  const enKeys = Object.keys(enLeaves)

  it('cover the agreed namespaces', () => {
    expect(Object.keys(itMessages).sort()).toEqual([...NAMESPACES].sort())
    expect(Object.keys(enMessages).sort()).toEqual([...NAMESPACES].sort())
  })

  it('have exactly the same keys in Italian and English', () => {
    const missingInEnglish = itKeys.filter((k) => !(k in enLeaves))
    const missingInItalian = enKeys.filter((k) => !(k in itLeaves))
    expect(missingInEnglish).toEqual([])
    expect(missingInItalian).toEqual([])
    expect(enKeys.length).toBe(itKeys.length)
  })

  it('have no empty message and no key containing a dot', () => {
    for (const key of itKeys) {
      expect(itLeaves[key].trim(), key).not.toBe('')
      expect(enLeaves[key].trim(), key).not.toBe('')
    }
    const walk = (tree: Tree) => {
      for (const [key, value] of Object.entries(tree)) {
        expect(key).not.toContain('.')
        if (typeof value !== 'string') walk(value)
      }
    }
    walk(itMessages as Tree)
    walk(enMessages as Tree)
  })

  it('use the same arguments and tags in both languages', () => {
    for (const key of itKeys) {
      expect(placeholders(enLeaves[key] ?? ''), key).toEqual(placeholders(itLeaves[key]))
    }
  })

  it('keep the official act names per language', () => {
    expect(itLeaves['ui.acts.AI_ACT']).toBe('Regolamento (UE) 2024/1689')
    expect(enLeaves['ui.acts.AI_ACT']).toBe('Regulation (EU) 2024/1689')
    expect(itLeaves['ui.frameworks.TAXONOMY']).toBe('Tassonomia')
    expect(enLeaves['ui.frameworks.TAXONOMY']).toBe('Taxonomy')
  })
})
