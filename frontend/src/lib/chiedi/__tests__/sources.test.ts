import { describe, it, expect } from 'vitest'
import {
  citationToSource,
  citationsToSources,
  isCelex,
  isUsefulUrl,
  normalizeFramework,
  sseCitationToChiedi,
} from '../sources'
import type { ChiediCitation } from '../types'
import { textContextFor } from '@/test/i18n'

const it_ = textContextFor('it')
const en = textContextFor('en')

describe('normalizeFramework', () => {
  it('maps the labels the backend and the demo use to the canonical keys', () => {
    expect(normalizeFramework('AI Act')).toBe('AI_ACT')
    expect(normalizeFramework('ai_act')).toBe('AI_ACT')
    expect(normalizeFramework('EU Taxonomy')).toBe('TAXONOMY')
    expect(normalizeFramework('NIS 2')).toBe('NIS2')
    expect(normalizeFramework('gdpr')).toBe('GDPR')
    expect(normalizeFramework('')).toBe('')
    expect(normalizeFramework(undefined)).toBe('')
  })
})

describe('isCelex / isUsefulUrl', () => {
  it('accepts real CELEX numbers and rejects article references', () => {
    expect(isCelex('32024R1689')).toBe(true)
    expect(isCelex('32022L2464')).toBe(true)
    expect(isCelex('52021PC0206')).toBe(true)
    expect(isCelex('Art. 19a(1)')).toBe(false)
    expect(isCelex('')).toBe(false)
    expect(isCelex(undefined)).toBe(false)
  })

  it('rejects the empty EUR-Lex link the stream falls back to', () => {
    expect(isUsefulUrl('https://eur-lex.europa.eu/eli/')).toBe(false)
    expect(isUsefulUrl('https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:32024R1689')).toBe(true)
    expect(isUsefulUrl('ftp://example.org/x')).toBe(false)
    expect(isUsefulUrl('not a url')).toBe(false)
  })
})

describe('citationToSource', () => {
  it('is verified only when the citation says so', () => {
    const base: ChiediCitation = { framework: 'AI_ACT', reference: 'art. 50, par. 1', quote_snippet: 'siano informate' }
    expect(citationToSource({ ...base, verified: true }, 1, 'a', it_).status).toBe('verified')
    expect(citationToSource({ ...base, verified: false }, 1, 'a', it_).status).toBe('unverified')
    expect(citationToSource(base, 1, 'a', it_).status).toBe('unverified')
  })

  it('derives the act, the CELEX and the EUR-Lex link from the framework', () => {
    const s = citationToSource(
      { framework: 'AI Act', reference: 'art. 50, par. 1', quote_snippet: 'siano informate del fatto', verified: true },
      2,
      'msg',
      it_,
    )
    expect(s.id).toBe('msg-2')
    expect(s.index).toBe(2)
    expect(s.act).toBe('Regolamento (UE) 2024/1689 (AI Act)')
    expect(s.article).toBe('art. 50, par. 1')
    expect(s.celex).toBe('32024R1689')
    expect(s.url).toBe('https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:32024R1689')
    expect(s.origin).toBe('EUR-Lex')
    expect(s.quote).toBe('siano informate del fatto')
  })

  it('names the act and links the English text when the interface is English', () => {
    const s = citationToSource({ framework: 'TAXONOMY', reference: 'art. 8', quote_snippet: '' }, 1, 'msg', en)
    expect(s.act).toBe('Regulation (EU) 2020/852 (Taxonomy)')
    expect(s.url).toBe('https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32020R0852')
  })

  it('keeps an explicit CELEX, URL and title over the table', () => {
    const s = citationToSource(
      {
        framework: 'CSRD',
        title: 'Direttiva (UE) 2026/470 (Omnibus I)',
        reference: 'art. 1',
        quote_snippet: '',
        celex: '32026L0470',
        url: 'https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2024;125',
      },
      1,
      'x',
      it_,
    )
    expect(s.act).toBe('Direttiva (UE) 2026/470 (Omnibus I)')
    expect(s.celex).toBe('32026L0470')
    expect(s.url).toContain('normattiva.it')
    expect(s.origin).toBe('Normattiva')
    expect(s.quote).toBeUndefined()
  })

  it('ignores a CELEX field that is not a CELEX number', () => {
    const s = citationToSource({ framework: 'GDPR', reference: 'art. 17', quote_snippet: 'x', celex: 'Art. 17' }, 1, 'x', it_)
    expect(s.celex).toBe('32016R0679')
    expect(s.url).toContain('CELEX:32016R0679')
  })

  it('leaves an unknown framework without a link rather than inventing one', () => {
    const s = citationToSource({ framework: 'D.Lgs. 125/2024', reference: 'art. 3', quote_snippet: '' }, 1, 'x', it_)
    expect(s.act).toBe('D.LGS. 125/2024')
    expect(s.celex).toBeUndefined()
    expect(s.url).toBeUndefined()
    expect(s.status).toBe('unverified')
  })

  it('numbers sources from 1 in order', () => {
    const sources = citationsToSources(
      [
        { framework: 'DORA', reference: 'art. 6', quote_snippet: 'a' },
        { framework: 'NIS2', reference: 'art. 23', quote_snippet: 'b' },
      ],
      'm',
      it_,
    )
    expect(sources.map((s) => s.index)).toEqual([1, 2])
    expect(sources.map((s) => s.id)).toEqual(['m-1', 'm-2'])
  })
})

describe('sseCitationToChiedi', () => {
  it('reads the fields of a stream event defensively', () => {
    // The generator puts the article reference in `celex` and the framework key
    // in `title` when the agent gave nothing better, and a bare /eli/ link.
    const c = sseCitationToChiedi({
      type: 'citation',
      celex: 'Art. 19a(1)',
      urn: null,
      article: 'Art. 19a(1)',
      title: 'CSRD',
      url: 'https://eur-lex.europa.eu/eli/',
      verified: false,
    })
    expect(c.framework).toBe('CSRD')
    expect(c.reference).toBe('Art. 19a(1)')
    expect(c.celex).toBeUndefined()
    expect(c.url).toBeUndefined()
    expect(c.verified).toBe(false)
    expect(c.title).toBeUndefined()
    const s = citationToSource(c, 1, 's', it_)
    expect(s.act).toBe('Direttiva (UE) 2022/2464 (CSRD)')
    expect(s.url).toContain('CELEX:32022L2464')
    expect(s.status).toBe('unverified')
  })

  it('keeps a real CELEX, link and title, and the verified flag', () => {
    const c = sseCitationToChiedi({
      type: 'citation',
      celex: '32024R1689',
      urn: null,
      article: 'art. 50',
      title: 'Regulation (EU) 2024/1689',
      url: 'https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:32024R1689',
      verified: true,
    })
    expect(c.framework).toBe('AI_ACT')
    expect(c.celex).toBe('32024R1689')
    expect(c.title).toBe('Regulation (EU) 2024/1689')
    expect(c.verified).toBe(true)
    const s = citationToSource(c, 1, 's', it_)
    expect(s.act).toBe('Regulation (EU) 2024/1689')
    expect(s.status).toBe('verified')
  })
})

describe('verified citations from the deterministic verifier', () => {
  const verified: ChiediCitation = {
    framework: 'AI_ACT',
    reference: 'Art. 50',
    quote_snippet: 'le persone sappiano che parlano con una IA',
    verified: true,
    match: 'exact',
    level: 'article',
    celex: '32024R1689',
    article: 'Art. 50',
    paragraph: '1',
    url: 'https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:32024R1689',
    official_quote: 'siano informate del fatto che stanno interagendo con un sistema di IA',
  }

  it('shows the official wording, never the model paraphrase', () => {
    const s = citationToSource(verified, 1, 's', it_)
    expect(s.status).toBe('verified')
    expect(s.quote).toBe('siano informate del fatto che stanno interagendo con un sistema di IA')
    expect(s.article).toBe('Art. 50, par. 1')
    expect(s.url).toContain('CELEX:32024R1689')
  })

  it('names the act where the passage really is when it sits in another act', () => {
    const elsewhere: ChiediCitation = {
      ...verified,
      framework: 'GDPR',
      reference: 'Art. 13',
      level: 'any',
      celex: '32026R1744',
      article: 'Art. 1',
      paragraph: null,
      url: 'https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32026R1744',
    }
    const s = citationToSource(elsewhere, 1, 's', en)
    expect(s.act).toBe('Regulation (EU) 2026/1744')
    expect(s.article).toBe('Art. 1')
    expect(s.status).toBe('verified')
  })

  it('keeps the model quote and reference for an unverified citation', () => {
    const s = citationToSource(
      { ...verified, verified: false, match: null, level: null, celex: null, url: null, official_quote: null, article: null, paragraph: null },
      1,
      's',
      it_,
    )
    expect(s.status).toBe('unverified')
    expect(s.quote).toBe('le persone sappiano che parlano con una IA')
    expect(s.article).toBe('Art. 50')
  })

  it('reads the official quote of a verified stream citation', () => {
    const c = sseCitationToChiedi({
      type: 'citation',
      framework: 'AI_ACT',
      celex: '32024R1689',
      article: 'Art. 113',
      title: 'Artificial Intelligence Act',
      url: 'https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1689',
      quote: 'It shall apply from 2 August 2026.',
      verified: true,
      match: 'exact',
      level: 'article',
    })
    expect(c.official_quote).toBe('It shall apply from 2 August 2026.')
    expect(c.quote_snippet).toBe('')
    const s = citationToSource(c, 1, 's', en)
    expect(s.quote).toBe('It shall apply from 2 August 2026.')
    expect(s.status).toBe('verified')
  })
})
