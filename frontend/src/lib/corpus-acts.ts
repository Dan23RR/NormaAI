/**
 * The EU acts of the question-and-answer corpus.
 *
 * A mirror of TRACKED_ACTS in src/crawler/eurlex/client.py, the registry the
 * backend builds the corpus from. The public pages name these acts and only
 * these: a test compares this list with the Python registry, so the site
 * cannot list a text that is not in the corpus, nor leave one out.
 */
import type { Translate } from '@/i18n/types'

/** The areas, in the order of FRAMEWORK_ORDER; each is a key of `ui.frameworks`. */
export const CORPUS_AREAS = ['CSRD', 'CSDDD', 'AI_ACT', 'DORA', 'NIS2', 'TAXONOMY', 'GDPR', 'CRA'] as const
export type CorpusArea = (typeof CORPUS_AREAS)[number]

/** How an act is named; the values are the `eli_type` of the registry. */
export type ActKind = 'dir' | 'reg' | 'reg_del' | 'reg_impl'

export interface CorpusAct {
  /** CELEX number of the act as adopted, e.g. "32024R1689". */
  celex: string
  /** The area the registry files the act under (an amending act is listed once, there). */
  area: CorpusArea
  kind: ActKind
}

export const CORPUS_ACTS: readonly CorpusAct[] = [
  { celex: '32022L2464', area: 'CSRD', kind: 'dir' },
  { celex: '32013L0034', area: 'CSRD', kind: 'dir' },
  { celex: '32023R2772', area: 'CSRD', kind: 'reg_del' },
  { celex: '32025L0794', area: 'CSRD', kind: 'dir' },
  { celex: '32026L0470', area: 'CSRD', kind: 'dir' },
  { celex: '32024L1760', area: 'CSDDD', kind: 'dir' },
  { celex: '32024R1689', area: 'AI_ACT', kind: 'reg' },
  { celex: '32026R1744', area: 'AI_ACT', kind: 'reg' },
  { celex: '32022R2554', area: 'DORA', kind: 'reg' },
  { celex: '32024R1773', area: 'DORA', kind: 'reg_del' },
  { celex: '32024R1774', area: 'DORA', kind: 'reg_del' },
  { celex: '32024R2956', area: 'DORA', kind: 'reg_impl' },
  { celex: '32022L2555', area: 'NIS2', kind: 'dir' },
  { celex: '32020R0852', area: 'TAXONOMY', kind: 'reg' },
  { celex: '32023R2486', area: 'TAXONOMY', kind: 'reg_del' },
  { celex: '32016R0679', area: 'GDPR', kind: 'reg' },
  { celex: '32024R2847', area: 'CRA', kind: 'reg' },
  { celex: '32025R2392', area: 'CRA', kind: 'reg_impl' },
]

/** The acts of one area, in the order of the registry. */
export function actsOf(area: CorpusArea): CorpusAct[] {
  return CORPUS_ACTS.filter((act) => act.area === area)
}

/** Year and number as the act is cited: "32024R1773" is 2024/1773, "32013L0034" is 2013/34. */
export function actNumber(celex: string): { year: string; number: string } {
  const m = /^3(\d{4})[A-Z](\d{4})$/.exec(celex)
  if (!m) throw new Error(`Not the CELEX of an act: ${celex}`)
  return { year: m[1], number: String(Number(m[2])) }
}

/**
 * The act as it is cited, built from its CELEX so that a number is never
 * typed twice: "Regolamento delegato (UE) 2023/2772", "Direttiva 2013/34/UE"
 * (directives before 2015 carry the year first and "UE" last).
 */
export function corpusActName(act: CorpusAct, t: Translate): string {
  const values = actNumber(act.celex)
  switch (act.kind) {
    case 'reg_del':
      return t('landing.sources.kinds.delegated', values)
    case 'reg_impl':
      return t('landing.sources.kinds.implementing', values)
    case 'reg':
      return t('ui.actRegulation', values)
    case 'dir':
      return t(Number(values.year) >= 2015 ? 'ui.actDirective' : 'ui.actDirectiveLegacy', values)
  }
}
