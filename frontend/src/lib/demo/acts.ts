/**
 * The example corpus date shown by the demo. Not a real corpus: a fixed day
 * on which every statement of the demo data was checked on the official
 * texts (EUR-Lex for EU law, Normattiva for Italian law).
 */
export const DEMO_CORPUS_AS_OF = '2026-11-10'

/**
 * The consolidated text each amended act is quoted from, by CELEX of the
 * basic act: the date is the one of the CELLAR consolidated version
 * (32024R1689 at 2026-07-27 is 02024R1689-20260727). An act that is not
 * listed is quoted from the text published in the Official Journal.
 * scripts/check_demo_quotes.py reads this table and looks for every demo
 * quote in the version named here, so a passage that an amending act removed
 * fails the check.
 */
export const DEMO_ACT_VERSIONS: Record<string, string> = {
  // AI Act as amended by Regulation (EU) 2026/1744
  '32024R1689': '2026-07-27',
  // Accounting Directive, CSRD and CSDDD as amended by Directive (EU) 2026/470
  '32013L0034': '2026-03-18',
  '32022L2464': '2026-03-18',
  '32024L1760': '2026-03-18',
}
