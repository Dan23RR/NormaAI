import { describe, it, expect } from 'vitest'
import {
  actNameFromCelex,
  actOfCelex,
  citationToSource,
  citationsToSources,
  isCelex,
  isUsefulUrl,
  markerLabel,
  nearMatchOf,
  normalizeFramework,
  sseCitationToChiedi,
  withActNames,
} from '../sources'
import { buildCopyText } from '../copy'
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
    official_quote: 'siano informate del fatto di stare interagendo con un sistema di IA',
  }

  it('shows the official wording, never the model paraphrase', () => {
    const s = citationToSource(verified, 1, 's', it_)
    expect(s.status).toBe('verified')
    expect(s.quote).toBe('siano informate del fatto di stare interagendo con un sistema di IA')
    expect(s.article).toBe('Art. 50, par. 1')
    expect(s.url).toContain('CELEX:32024R1689')
  })

  it('never shows as verified a passage an older answer found in another act', () => {
    // Before the backend reported `found_elsewhere`, such a citation came "verified" at level "any".
    const legacy: ChiediCitation = {
      ...verified,
      framework: 'GDPR',
      reference: 'Art. 13',
      level: 'any',
      celex: '32026R1744',
      article: 'Art. 1',
      paragraph: null,
      url: 'https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32026R1744',
    }
    const s = citationToSource(legacy, 1, 's', en)
    expect(s.status).toBe('unverified')
    expect(s.act).toBe('Regulation (EU) 2016/679 (GDPR)')
    expect(s.article).toBe('Art. 13')
    expect(s.quote).toBeUndefined()
    expect(s.elsewhere).toEqual({
      where: 'act',
      location: 'Regulation (EU) 2026/1744, Art. 1',
      quote: 'siano informate del fatto di stare interagendo con un sistema di IA',
      url: 'https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32026R1744',
    })
    // ... and the same for another article of the act, at level "framework".
    const article = citationToSource({ ...verified, reference: 'Art. 52', level: 'framework' }, 1, 's', it_)
    expect(article.status).toBe('unverified')
    expect(article.elsewhere?.where).toBe('article')
    expect(article.elsewhere?.location).toBe('Art. 50, par. 1')
    // A verified citation of an article in the act cited is not touched.
    expect(citationToSource({ ...verified, level: 'framework', reference: 'Art. 50' }, 1, 's', it_).status).toBe('verified')
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

describe('a quote found in another act, article or paragraph', () => {
  // The backend (annotate_citations): not verified, with where the wording really is.
  const elsewhere: ChiediCitation = {
    framework: 'GDPR',
    reference: 'Art. 6',
    quote_snippet: 'garantiscono che gli output del sistema di IA siano marcati',
    verified: false,
    found_elsewhere: true,
    found_in: 'act',
    found_celex: '32024R1689',
    found_article: 'Art. 50',
    found_paragraph: '2',
    found_quote: 'garantiscono che gli output del sistema di IA siano marcati',
    found_url: 'https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:32024R1689',
  }

  it('is never verified and names the act the answer cites', () => {
    const s = citationToSource(elsewhere, 1, 's', it_)
    expect(s.status).toBe('unverified')
    expect(s.act).toBe('Regolamento (UE) 2016/679 (GDPR)')
    expect(s.article).toBe('Art. 6')
    expect(s.celex).toBe('32016R0679')
    expect(s.quote).toBeUndefined()
  })

  it('says where the text really is', () => {
    expect(citationToSource(elsewhere, 1, 's', it_).elsewhere).toEqual({
      where: 'act',
      location: 'Regolamento (UE) 2024/1689 (AI Act), Art. 50, par. 2',
      quote: 'garantiscono che gli output del sistema di IA siano marcati',
      url: 'https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:32024R1689',
    })
    const article = citationToSource({ ...elsewhere, found_in: 'article', found_paragraph: null }, 1, 's', en)
    expect(article.elsewhere?.location).toBe('Art. 50')
    expect(it_.t('chiedi.elsewhere.act', { location: 'X' })).toBe('Testo trovato in un altro atto: X')
    expect(en.t('chiedi.elsewhere.paragraph', { location: 'X' })).toBe('Text found in another paragraph of the same article: X')
  })

  it('reads the place from a stream event that is not verified', () => {
    const event = {
      type: 'citation' as const,
      framework: 'GDPR',
      celex: '32016R0679',
      article: 'Art. 6',
      title: 'GDPR',
      quote: elsewhere.quote_snippet,
      verified: false,
      found_elsewhere: true,
      found_in: 'act' as const,
      found_celex: '32024R1689',
      found_article: 'Art. 50',
      found_paragraph: '2',
      found_quote: elsewhere.found_quote as string,
      found_url: elsewhere.found_url as string,
    }
    const c = sseCitationToChiedi(event)
    expect(c.found_elsewhere).toBe(true)
    expect(c.found_celex).toBe('32024R1689')
    expect(citationToSource(c, 1, 's', it_).elsewhere?.location).toBe('Regolamento (UE) 2024/1689 (AI Act), Art. 50, par. 2')
    expect(sseCitationToChiedi({ ...event, verified: true }).found_elsewhere).toBeUndefined()
  })

  it('copies the quote with where it was found', () => {
    const text = buildCopyText({ answer: 'x [1]', sources: citationsToSources([elsewhere], 'm', it_) }, it_)
    expect(text).toContain(
      '1. Regolamento (UE) 2016/679 (GDPR), Art. 6: «garantiscono che gli output del sistema di IA siano marcati» ' +
        '(da verificare; testo trovato altrove: Regolamento (UE) 2024/1689 (AI Act), Art. 50, par. 2)',
    )
  })
})

describe('actNameFromCelex', () => {
  it('names acts from 2015 on with the (EU) year/number form', () => {
    expect(actNameFromCelex('32026R1744', it_.t)).toBe('Regolamento (UE) 2026/1744')
    expect(actNameFromCelex('32022L2464', en.t)).toBe('Directive (EU) 2022/2464')
  })

  it('names 2010-2014 directives with the year/number/EU form', () => {
    expect(actNameFromCelex('32013L0034', it_.t)).toBe('Direttiva 2013/34/UE')
    expect(actNameFromCelex('32013L0034', en.t)).toBe('Directive 2013/34/EU')
  })

  it('shows the CELEX for older regulations, whose numbering differs', () => {
    expect(actNameFromCelex('32013R0575', en.t)).toContain('32013R0575')
  })
})

describe('articles verified in the act that amends them', () => {
  // Backend case B (src/agents/quoted_articles.py): the cited article is the
  // amended act's, its wording was found in the amending act, which the link opens.
  const amended: ChiediCitation = {
    framework: '32019R2088',
    reference: 'Art. 2a',
    quote_snippet: '',
    verified: true,
    celex: '32019R2088',
    article: 'Art. 2a',
    official_quote: 'The European Supervisory Authorities shall develop draft regulatory technical standards',
    url: 'https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:32020R0852',
    amending_celex: '32020R0852',
    amending_article: 'Art. 25',
  }

  it('names the amended act and says where the wording was verified', () => {
    const s = citationToSource(amended, 1, 'a', it_)
    expect(s.act).toBe('Regolamento (UE) 2019/2088')
    expect(s.article).toBe('Art. 2a')
    expect(s.note).toBe(`Testo verificato in ${actOfCelex('32020R0852', it_.t)}, Art. 25, che lo modifica`)
    expect(s.url).toBe(amended.url)
    expect(citationToSource(amended, 1, 'a', en).note).toBe(
      `Wording verified in ${actOfCelex('32020R0852', en.t)}, Art. 25, which amends it`,
    )
  })

  it('has no note when the citation is not verified or not quoted', () => {
    expect(citationToSource({ ...amended, verified: false }, 1, 'a', it_).note).toBeUndefined()
    expect(citationToSource({ ...amended, amending_celex: null }, 1, 'a', it_).note).toBeUndefined()
  })

  it('reads the amending act from a verified stream event only', () => {
    const event = {
      type: 'citation' as const,
      celex: '32019R2088',
      article: 'Art. 2a',
      title: '32019R2088',
      verified: true,
      amending_celex: '32020R0852',
      amending_article: 'Art. 25',
    }
    expect(sseCitationToChiedi(event).amending_celex).toBe('32020R0852')
    expect(sseCitationToChiedi(event).amending_article).toBe('Art. 25')
    expect(sseCitationToChiedi({ ...event, verified: false }).amending_celex).toBeUndefined()
  })
})

describe('actOfCelex', () => {
  it('uses the framework table first, the CELEX number otherwise', () => {
    expect(actOfCelex('32024R1689', en.t)).toBe('Regulation (EU) 2024/1689 (AI Act)')
    expect(actOfCelex('32026R1744', it_.t)).toBe('Regolamento (UE) 2026/1744')
  })
})

describe('an act cited by its CELEX', () => {
  // The backend labels an act other than the main one of its framework with its
  // CELEX (src/agents/llm.py, _citation_key): the Digital Omnibus on AI is no
  // article of the AI Act, the Accounting Directive none of the CSRD.
  it('names the act in the source, with its CELEX and link, verified or not', () => {
    const omnibus: ChiediCitation = { framework: '32026R1744', reference: 'Art. 1', quote_snippet: 'il regolamento è così modificato' }
    const s = citationToSource(omnibus, 1, 's', it_)
    expect(s.act).toBe('Regolamento (UE) 2026/1744')
    expect(s.celex).toBe('32026R1744')
    expect(s.url).toBe('https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:32026R1744')
    expect(s.status).toBe('unverified')
    const verifiedOmnibus = citationToSource({ ...omnibus, verified: true, celex: '32026R1744', article: 'Art. 1' }, 1, 's', en)
    expect(verifiedOmnibus.act).toBe('Regulation (EU) 2026/1744')
    expect(verifiedOmnibus.status).toBe('verified')
    expect(citationToSource({ framework: '32013L0034', reference: 'Art. 3', quote_snippet: '' }, 1, 's', it_).act).toBe('Direttiva 2013/34/UE')
    // The CELEX of a main act stays that act, with its short name.
    const aiAct = citationToSource({ framework: '32024R1689', reference: 'Art. 4', quote_snippet: '' }, 1, 's', it_)
    expect(aiAct.act).toBe('Regolamento (UE) 2024/1689 (AI Act)')
  })

  it('shows the act name in the bracketed references of the answer', () => {
    expect(markerLabel('32026R1744, Art. 1', it_.t)).toBe('Regolamento (UE) 2026/1744, Art. 1')
    expect(markerLabel('32026R1744, Recital 38', en.t)).toBe('Regulation (EU) 2026/1744, Recital 38')
    expect(markerLabel('32013L0034, Art. 3(4)', en.t)).toBe('Directive 2013/34/EU, Art. 3(4)')
    expect(markerLabel('AI_ACT, Art. 50', it_.t)).toBe('AI_ACT, Art. 50')
    expect(markerLabel('1', it_.t)).toBe('1')
    expect(withActNames('Si applica [32026R1744, Art. 1] e [GDPR, Art. 6].', it_.t)).toBe(
      'Si applica [Regolamento (UE) 2026/1744, Art. 1] e [GDPR, Art. 6].',
    )
  })

  it('keeps the CELEX of a stream event as the framework', () => {
    const c = sseCitationToChiedi({ type: 'citation', framework: '32026R1744', celex: '32026R1744', article: 'Art. 1', title: '32026R1744', verified: false })
    expect(c.framework).toBe('32026R1744')
    expect(citationToSource(c, 1, 's', it_).act).toBe('Regolamento (UE) 2026/1744')
  })

  it('copies the answer with the act names', () => {
    const sources = citationsToSources([{ framework: '32026R1744', reference: 'Art. 1', quote_snippet: '' }], 'm', it_)
    const text = buildCopyText({ answer: 'Il calendario cambia [32026R1744, Art. 1].', sources }, it_)
    expect(text.startsWith('Il calendario cambia [Regolamento (UE) 2026/1744, Art. 1].')).toBe(true)
    expect(text).toContain('1. Regolamento (UE) 2026/1744, Art. 1')
  })
})

describe('a quote that differs from the official text', () => {
  // The verifier's near match (src/agents/citation_verifier.py): not verified, with the
  // official wording it almost matched, where it is and the words that differ.
  const altered: ChiediCitation = {
    framework: 'GDPR',
    reference: 'Art. 33, par. 1',
    quote_snippet: 'senza ingiustificato ritardo e, ove possibile, entro 48 ore dal momento in cui ne è venuto a conoscenza',
    verified: false,
    celex: '32016R0679',
    near_quote: 'senza ingiustificato ritardo e, ove possibile, entro 72 ore dal momento in cui ne è venuto a conoscenza',
    near_article: 'Art. 33',
    differences: [{ quoted: '48', official: '72' }],
  }

  it('stays unverified and carries what the official text says instead', () => {
    const s = citationToSource(altered, 1, 's', it_)
    expect(s.status).toBe('unverified')
    expect(s.act).toBe('Regolamento (UE) 2016/679 (GDPR)')
    expect(s.article).toBe('Art. 33, par. 1')
    expect(s.near).toEqual({
      quoted: altered.quote_snippet,
      official: altered.near_quote,
      article: 'Art. 33',
      differences: [{ quoted: '48', official: '72' }],
    })
  })

  it('does not show the altered words as the passage of law', () => {
    // `quote` is what the margin puts under the highlighter: never a wording known to be wrong.
    expect(citationToSource(altered, 1, 's', it_).quote).toBeUndefined()
  })

  it('never gives a near match to a verified citation, nor to one without the official wording', () => {
    expect(nearMatchOf({ ...altered, verified: true })).toBeUndefined()
    expect(citationToSource({ ...altered, verified: true, official_quote: altered.near_quote }, 1, 's', it_).near).toBeUndefined()
    expect(nearMatchOf({ ...altered, near_quote: null })).toBeUndefined()
    expect(nearMatchOf({ ...altered, near_quote: '   ' })).toBeUndefined()
    const plain = citationToSource({ ...altered, near_quote: undefined, differences: undefined }, 1, 's', it_)
    expect(plain.near).toBeUndefined()
    expect(plain.quote).toBe(altered.quote_snippet)
  })

  it('drops empty differences and keeps a word only one side has', () => {
    const near = nearMatchOf({
      ...altered,
      near_article: null,
      differences: [
        { quoted: '', official: 'non' },
        { quoted: ' ', official: '' },
        { quoted: 'sempre', official: '' },
      ],
    })
    expect(near?.article).toBeUndefined()
    expect(near?.differences).toEqual([
      { quoted: '', official: 'non' },
      { quoted: 'sempre', official: '' },
    ])
  })

  it('reads the near match of a stream event, only when the event is not verified', () => {
    const event = {
      type: 'citation' as const,
      framework: 'GDPR',
      celex: '32016R0679',
      article: 'Art. 33',
      title: 'GDPR',
      quote: altered.quote_snippet,
      verified: false,
      near_quote: altered.near_quote as string,
      near_article: 'Art. 33',
      differences: [{ quoted: '48', official: '72' }],
    }
    const c = sseCitationToChiedi(event)
    expect(c.verified).toBe(false)
    expect(c.quote_snippet).toBe(altered.quote_snippet)
    expect(c.near_quote).toBe(altered.near_quote)
    expect(c.near_article).toBe('Art. 33')
    expect(c.differences).toEqual([{ quoted: '48', official: '72' }])
    expect(citationToSource(c, 1, 's', en).near?.official).toBe(altered.near_quote)

    const verified = sseCitationToChiedi({ ...event, verified: true })
    expect(verified.near_quote).toBeUndefined()
    expect(verified.near_article).toBeUndefined()
    expect(verified.differences).toBeUndefined()
  })

  it('copies the answer quote with the official wording next to it', () => {
    const sources = citationsToSources([altered, { framework: 'GDPR', reference: 'Art. 34', quote_snippet: 'x', verified: true, official_quote: 'testo ufficiale' }], 'm', it_)
    const text = buildCopyText({ answer: 'Entro 48 ore [1].', sources }, it_)
    expect(text).toContain(
      '1. Regolamento (UE) 2016/679 (GDPR), Art. 33, par. 1: «senza ingiustificato ritardo e, ove possibile, entro 48 ore dal momento in cui ne è venuto a conoscenza» ' +
        '(da verificare; diversa dal testo ufficiale, che dice «senza ingiustificato ritardo e, ove possibile, entro 72 ore dal momento in cui ne è venuto a conoscenza»)',
    )
    expect(text).toContain('2. Regolamento (UE) 2016/679 (GDPR), Art. 34: «testo ufficiale» (verificata)')
    const english = buildCopyText({ answer: 'x', sources: citationsToSources([altered], 'm', en) }, en)
    expect(english).toContain('(unverified; differs from the official text, which says "senza ingiustificato ritardo')
  })
})
