import { describe, it, expect } from 'vitest'
import { changedSpan, diffRuns, diffWords, hasChanges, looseKey, splitWords } from '../word-diff'

const kinds = (before: string, after: string) => diffWords(before, after).map((s) => [s.kind, s.text])

describe('diffWords', () => {
  it('gives one unchanged segment for the same wording, whatever the line breaks', () => {
    const segments = diffWords('Articolo 33\nNotifica di una violazione', 'Articolo 33 Notifica  di una violazione')
    expect(segments).toEqual([{ kind: 'equal', text: 'Articolo 33 Notifica di una violazione', count: 6 }])
    expect(hasChanges(segments)).toBe(false)
  })

  it('finds a changed number between unchanged words, removed before added', () => {
    expect(kinds('ove possibile, entro 48 ore dal momento', 'ove possibile, entro 72 ore dal momento')).toEqual([
      ['equal', 'ove possibile, entro'],
      ['removed', '48'],
      ['added', '72'],
      ['equal', 'ore dal momento'],
    ])
  })

  it('reports words only added and words only removed', () => {
    expect(kinds('il titolare notifica la violazione', 'il titolare del trattamento notifica la violazione')).toEqual([
      ['equal', 'il titolare'],
      ['added', 'del trattamento'],
      ['equal', 'notifica la violazione'],
    ])
    expect(kinds('entro e non oltre 72 ore', 'entro 72 ore')).toEqual([
      ['equal', 'entro'],
      ['removed', 'e non oltre'],
      ['equal', '72 ore'],
    ])
    expect(kinds('', 'testo nuovo')).toEqual([['added', 'testo nuovo']])
    expect(kinds('testo vecchio', '')).toEqual([['removed', 'testo vecchio']])
    expect(kinds('', '')).toEqual([])
  })

  it('groups a rewritten stretch as one removal followed by one addition', () => {
    const before = 'adottano misure per garantire nella misura del possibile un livello sufficiente di alfabetizzazione in materia di IA'
    const after = "adottano misure volte a sostenere lo sviluppo dell'alfabetizzazione in materia di IA"
    expect(kinds(before, after)).toEqual([
      ['equal', 'adottano misure'],
      ['removed', 'per garantire nella misura del possibile un livello sufficiente di alfabetizzazione'],
      ['added', "volte a sostenere lo sviluppo dell'alfabetizzazione"],
      ['equal', 'in materia di IA'],
    ])
  })

  it('shortens long unchanged stretches and says how many words it left out', () => {
    const filler = Array.from({ length: 60 }, (_, i) => `parola${i}`).join(' ')
    const segments = diffWords(`${filler} entro 48 ore`, `${filler} entro 72 ore`, { collapse: { longerThan: 40, keep: 15 } })
    expect(segments.map((s) => s.kind)).toEqual(['equal', 'omitted', 'equal', 'removed', 'added', 'equal'])
    expect(segments[0].text.startsWith('parola0 parola1')).toBe(true)
    expect(segments[0].count).toBe(15)
    // 61 unchanged words (the filler and "entro"): 15 shown at each end, 31 left out.
    expect(segments[1]).toEqual({ kind: 'omitted', text: '', count: 31 })
    expect(segments[2].text.endsWith('parola59 entro')).toBe(true)
    expect(hasChanges(segments)).toBe(true)
  })

  it('leaves a stretch alone when it is not longer than the limit', () => {
    const filler = Array.from({ length: 40 }, (_, i) => `p${i}`).join(' ')
    const segments = diffWords(`${filler} a`, `${filler} b`, { collapse: { longerThan: 40, keep: 15 } })
    expect(segments.map((s) => s.kind)).toEqual(['equal', 'removed', 'added'])
    expect(segments[0].count).toBe(40)
  })

  it('stays exact on a long text with changes far apart', () => {
    const words = Array.from({ length: 6000 }, (_, i) => `w${i}`)
    const after = [...words]
    after[10] = 'ALFA'
    after[3000] = 'BETA'
    after.splice(5900, 2)
    const segments = diffWords(words.join(' '), after.join(' '))
    expect(segments.filter((s) => s.kind !== 'equal').map((s) => [s.kind, s.text])).toEqual([
      ['removed', 'w10'],
      ['added', 'ALFA'],
      ['removed', 'w3000'],
      ['added', 'BETA'],
      ['removed', 'w5900 w5901'],
    ])
    expect(segments.filter((s) => s.kind === 'equal').reduce((n, s) => n + s.count, 0)).toBe(6000 - 4)
  })
})

describe('splitWords', () => {
  it('keeps a number with spaces between its thousands in one word', () => {
    expect(splitWords('più di 1 000 dipendenti e un fatturato superiore a 450 000 000 EUR')).toEqual([
      'più',
      'di',
      '1 000',
      'dipendenti',
      'e',
      'un',
      'fatturato',
      'superiore',
      'a',
      '450 000 000',
      'EUR',
    ])
    // What is attached to the number stays with it; a non-breaking space separates thousands too.
    expect(splitWords('fino a 10 000 000 EUR, o al 2 %')).toEqual(['fino', 'a', '10 000 000', 'EUR,', 'o', 'al', '2', '%'])
    expect(splitWords('oltre 5\u00a0000;')).toEqual(['oltre', '5\u00a0000;'])
  })

  it('does not glue numbers that are not one number', () => {
    expect(splitWords('entro il 26 luglio 2027')).toEqual(['entro', 'il', '26', 'luglio', '2027'])
    expect(splitWords('gli articoli 8 e 11, da 25 a 39')).toEqual(['gli', 'articoli', '8', 'e', '11,', 'da', '25', 'a', '39'])
    expect(splitWords('il 1 2026 e il 12 2026')).toEqual(['il', '1', '2026', 'e', 'il', '12', '2026'])
    expect(splitWords('  \n ')).toEqual([])
  })

  it('makes a changed threshold read as one number replaced by another', () => {
    expect(
      diffWords(
        'più di 1 000 dipendenti e un fatturato netto superiore a 450 000 000 EUR',
        'più di 5 000 dipendenti e un fatturato netto superiore a 1 500 000 000 EUR',
      ).map((s) => [s.kind, s.text]),
    ).toEqual([
      ['equal', 'più di'],
      ['removed', '1 000'],
      ['added', '5 000'],
      ['equal', 'dipendenti e un fatturato netto superiore a'],
      ['removed', '450 000 000'],
      ['added', '1 500 000 000'],
      ['equal', 'EUR'],
    ])
  })
})

describe('diffRuns', () => {
  it('indexes both texts, end excluded', () => {
    const a = splitWords('entro 48 ore')
    const b = splitWords('entro 72 ore')
    expect(diffRuns(a, b)).toEqual([
      { kind: 'equal', a1: 0, a2: 1, b1: 0, b2: 1 },
      { kind: 'removed', a1: 1, a2: 2, b1: 1, b2: 1 },
      { kind: 'added', a1: 2, a2: 2, b1: 1, b2: 2 },
      { kind: 'equal', a1: 2, a2: 3, b1: 2, b2: 3 },
    ])
  })

  it('reports a full replacement when the texts differ by more words than the limit', () => {
    const a = splitWords('uno due tre quattro')
    const b = splitWords('cinque sei sette otto')
    expect(diffRuns(a, b, (w) => w, 3)).toEqual([
      { kind: 'removed', a1: 0, a2: 4, b1: 0, b2: 0 },
      { kind: 'added', a1: 4, a2: 4, b1: 0, b2: 4 },
    ])
    // With room for every edit the result is the same, found by the algorithm itself.
    expect(diffRuns(a, b).map((r) => r.kind)).toEqual(['removed', 'added'])
  })
})

describe('looseKey', () => {
  it('forgives case, accents, apostrophes and the punctuation around a word', () => {
    expect(looseKey('Autorità,')).toBe(looseKey('autorita'))
    // The official texts use the typographic apostrophe (U+2019), documents often the plain one.
    expect(looseKey('dell’alfabetizzazione')).toBe(looseKey("dell'alfabetizzazione"))
    expect(looseKey('«conoscenza».')).toBe('conoscenza')
    expect(looseKey('perché')).toBe('perche')
  })

  it('never makes two different numbers or words equal', () => {
    expect(looseKey('48')).not.toBe(looseKey('72'))
    expect(looseKey('non')).not.toBe(looseKey('ne'))
    expect(looseKey('(72)')).toBe('72')
  })
})

describe('changedSpan', () => {
  const official = 'senza ingiustificato ritardo e, ove possibile, entro 72 ore dal momento in cui ne è venuto a conoscenza'

  it('points at the official words a quote changed', () => {
    const quoted = 'senza ingiustificato ritardo e, ove possibile, entro 48 ore dal momento in cui ne è venuto a conoscenza'
    expect(changedSpan(quoted, official)).toEqual({
      before: 'senza ingiustificato ritardo e, ove possibile, entro',
      changed: '72',
      after: 'ore dal momento in cui ne è venuto a conoscenza',
    })
  })

  it('points at the official words a quote dropped', () => {
    expect(changedSpan('il titolare notifica la violazione', 'il titolare non notifica la violazione')).toEqual({
      before: 'il titolare',
      changed: 'non',
      after: 'notifica la violazione',
    })
  })

  it('ignores what the verifier forgives: case, accents, punctuation', () => {
    const quoted = 'Senza ingiustificato ritardo e ove possibile entro 72 ore dal momento in cui ne e venuto a conoscenza.'
    expect(changedSpan(quoted, official)).toBeNull()
  })

  it('gives up when the difference is in more than one place, or is a word the quote adds', () => {
    expect(changedSpan('entro 48 ore dal giorno in cui', 'entro 72 ore dal momento in cui')).toBeNull()
    expect(changedSpan('entro e non oltre 72 ore', 'entro 72 ore')).toBeNull()
  })
})
