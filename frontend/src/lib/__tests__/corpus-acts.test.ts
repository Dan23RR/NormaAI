import { describe, it, expect } from 'vitest'
import { existsSync, readFileSync } from 'node:fs'
import path from 'node:path'
import { translatorFor } from '@/test/i18n'
import { CORPUS_ACTS, CORPUS_AREAS, actNumber, actsOf, corpusActName } from '../corpus-acts'

// The registry the backend builds the corpus from. It sits outside the
// frontend folder: a copy of the frontend alone (a container build context)
// has no file to compare with, and the comparison is skipped there.
const REGISTRY = path.resolve(__dirname, '../../../../src/crawler/eurlex/client.py')

/** The tuple assigned to `name` in the Python source, without the outer parentheses. */
function pythonTuple(source: string, name: string): string {
  const start = source.indexOf(`${name}: tuple[`)
  const open = source.indexOf('= (\n', start)
  const close = source.indexOf('\n)\n', open)
  if (start < 0 || open < 0 || close < 0) throw new Error(`${name} not found in the registry`)
  return source.slice(open + 3, close)
}

/** CELEX, framework and ELI type of every TrackedAct(...) of the registry, in order. */
function trackedActs(source: string) {
  return pythonTuple(source, 'TRACKED_ACTS')
    .split('TrackedAct(')
    .slice(1)
    .map((entry) => {
      const head = /^\s*"(3\d{4}[A-Z]\d{4})",\s*"([A-Z0-9_]+)"/.exec(entry)
      if (!head) throw new Error(`Unreadable registry entry: ${entry.slice(0, 60)}`)
      const kind = /eli_type="([a-z_]+)"/.exec(entry)
      return { celex: head[1], area: head[2], kind: kind ? kind[1] : 'reg' }
    })
}

describe('corpus acts', () => {
  it('lists each act once, under an area of the list', () => {
    const celex = CORPUS_ACTS.map((act) => act.celex)
    expect(new Set(celex).size).toBe(celex.length)
    for (const act of CORPUS_ACTS) expect(CORPUS_AREAS).toContain(act.area)
    for (const area of CORPUS_AREAS) expect(actsOf(area).length, area).toBeGreaterThan(0)
    expect(CORPUS_AREAS.flatMap((area) => actsOf(area))).toEqual(CORPUS_ACTS)
  })

  it('reads year and number from the CELEX', () => {
    expect(actNumber('32024R1773')).toEqual({ year: '2024', number: '1773' })
    expect(actNumber('32013L0034')).toEqual({ year: '2013', number: '34' })
    expect(actNumber('32016R0679')).toEqual({ year: '2016', number: '679' })
    expect(() => actNumber('02016R0679-20160504')).toThrow()
  })

  it('names each act as it is cited, in both languages', () => {
    const name = (celex: string, language: 'it' | 'en') => {
      const act = CORPUS_ACTS.find((a) => a.celex === celex)
      if (!act) throw new Error(`${celex} is not in the corpus`)
      return corpusActName(act, translatorFor(language))
    }
    expect(name('32016R0679', 'it')).toBe('Regolamento (UE) 2016/679')
    expect(name('32026L0470', 'it')).toBe('Direttiva (UE) 2026/470')
    expect(name('32013L0034', 'it')).toBe('Direttiva 2013/34/UE')
    expect(name('32023R2772', 'it')).toBe('Regolamento delegato (UE) 2023/2772')
    expect(name('32024R2956', 'it')).toBe('Regolamento di esecuzione (UE) 2024/2956')
    expect(name('32016R0679', 'en')).toBe('Regulation (EU) 2016/679')
    expect(name('32013L0034', 'en')).toBe('Directive 2013/34/EU')
    expect(name('32024R1774', 'en')).toBe('Delegated Regulation (EU) 2024/1774')
    expect(name('32025R2392', 'en')).toBe('Implementing Regulation (EU) 2025/2392')
    // Every name carries the number of its own CELEX, whatever the kind.
    for (const act of CORPUS_ACTS) {
      const { year, number } = actNumber(act.celex)
      expect(corpusActName(act, translatorFor('it')), act.celex).toContain(`${year}/${number}`)
      expect(corpusActName(act, translatorFor('en')), act.celex).toContain(`${year}/${number}`)
    }
  })
})

describe.skipIf(!existsSync(REGISTRY))('corpus acts and the backend registry', () => {
  // A Windows checkout may hold the file with CRLF line endings.
  const source = existsSync(REGISTRY) ? readFileSync(REGISTRY, 'utf-8').replace(/\r\n/g, '\n') : ''

  it('are the tracked acts of src/crawler/eurlex/client.py, in the same order', () => {
    expect(CORPUS_ACTS.map((act) => ({ ...act }))).toEqual(trackedActs(source))
  })

  it('use the areas of FRAMEWORK_ORDER, in the same order', () => {
    const order = Array.from(pythonTuple(source, 'FRAMEWORK_ORDER').matchAll(/"([A-Z0-9_]+)"/g), (m) => m[1])
    expect([...CORPUS_AREAS]).toEqual(order)
  })
})
