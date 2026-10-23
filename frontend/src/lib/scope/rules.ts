/**
 * Deterministic scope rules for CSRD, CSDDD and AI Act article 50.
 *
 * Every threshold and date is a port of what the repository states:
 *  - public/scope-csrd.html: EMP_T 1000, REV_T 450 (M€), cumulative AND,
 *    margin bands 850-1200 employees and 380-550 M€, listed companies
 *    under the thresholds as a border case, CSDDD 5000 employees and
 *    1,5 bn€, Omnibus I in force 18 March 2026, CELEX 32026L0470.
 *  - public/codex-post-omnibus-2025-2029.pdf: ch. 1.2 (CSRD table, non-EU
 *    threshold 450 M€ EU turnover), ch. 1.4 (CSDDD), ch. 2 (worked
 *    examples 600/120, 1200/380, 1500/620), ch. 5 (calendar).
 *  - public/scope-aiact.html: the four article 50 situations, who bears
 *    each obligation, exceptions, application 2 August 2026 (art. 113),
 *    sanctions art. 99(4) and 99(6), Legge 132/2025, the deferred
 *    high-risk dates, the transitional marking date 2 December 2026.
 *  - prompts/gap_analyst.txt and .planning/decisions/003: CSDDD
 *    transposition 26 July 2028, first compliance 26 July 2029.
 *
 * Anything the sources do not state (balance-sheet total, NIS2, DORA,
 * GDPR, CRA scope thresholds) is deliberately absent. The words of every
 * verdict live in the `ambito.rules` messages: this module decides, the
 * messages speak.
 */
import { eurlexLang } from '@/i18n/config'
import { formatDate, formatInt, formatMillionsEur } from '@/i18n/format'
import type { TextContext } from '@/i18n/types'
import { AI_ACT_ART_50_1_IT } from '@/lib/law-passages'
import type { Source } from '@/lib/sources'
import { eurlexUrl } from '@/lib/sources'
import { VERIFIED_ON, scopeSources, withIndex } from './sources'
import type {
  AiActAnswers,
  AiKey,
  AiObligation,
  LegalPassage,
  ScopeAssessment,
  ScopeInput,
  ScopeResult,
} from './types'
import { AI_KEY_FIELD } from './types'

export const CSRD_RULES = {
  employees: 1000,
  turnoverEur: 450_000_000,
  employeesMargin: { min: 850, max: 1200 },
  turnoverMarginEur: { min: 380_000_000, max: 550_000_000 },
  nonEuTurnoverEur: 450_000_000,
} as const

export const CSDDD_RULES = {
  employees: 5000,
  turnoverEur: 1_500_000_000,
} as const

export const SCOPE_DATES = {
  omnibusInForce: '2026-03-18',
  csdddTransposition: '2028-07-26',
  csdddFirstCompliance: '2029-07-26',
  aiActArt4And5: '2025-02-02',
  aiActGpai: '2025-08-02',
  aiActArt50: '2026-08-02',
  aiActLegacyMarking: '2026-12-02',
  aiActHighRiskAnnexIII: '2027-12-02',
  aiActHighRiskAnnexI: '2028-08-02',
} as const

export type CsrdBand = 'in' | 'filo' | 'out'

/** Exact port of classify() in public/scope-csrd.html. */
export function classifyCsrd(employees: number, turnoverEur: number, listed: boolean): CsrdBand {
  const empOver = employees > CSRD_RULES.employees
  const revOver = turnoverEur > CSRD_RULES.turnoverEur
  if (empOver && revOver) return 'in'
  if (empOver || revOver) return 'filo'
  const empMargin = employees >= CSRD_RULES.employeesMargin.min && employees <= CSRD_RULES.employeesMargin.max
  const revMargin = turnoverEur >= CSRD_RULES.turnoverMarginEur.min && turnoverEur <= CSRD_RULES.turnoverMarginEur.max
  if (empMargin || revMargin) return 'filo'
  if (listed) return 'filo'
  return 'out'
}

function csrdNotes(input: ScopeInput, ctx: TextContext): string[] {
  const notes: string[] = []
  if (input.wave1Reporter) notes.push(ctx.t('ambito.rules.csrd.noteWave1'))
  if (input.groupRole === 'parent') notes.push(ctx.t('ambito.rules.csrd.noteParent'))
  if (input.groupRole === 'subsidiary') notes.push(ctx.t('ambito.rules.csrd.noteSubsidiary'))
  return notes
}

function assessCsrd(input: ScopeInput, ctx: TextContext, S: ReturnType<typeof scopeSources>): ScopeResult {
  const { t, locale } = ctx
  const base = {
    framework: 'CSRD' as const,
    sources: withIndex([S.omnibusI, S.csrd, S.dlgs125, S.codex]),
    passages: [] as LegalPassage[],
    verifiedOn: VERIFIED_ON,
  }
  const fromLabel = t('ambito.rules.csrd.fromLabel', { date: formatDate(SCOPE_DATES.omnibusInForce, ctx) })

  if (input.nonEu) {
    if (input.euTurnoverEur == null) {
      return { ...base, status: 'not_assessed', headline: t('ambito.rules.csrd.nonEuMissing'), reasons: [], notes: [] }
    }
    const amounts = {
      amount: formatMillionsEur(input.euTurnoverEur, ctx),
      threshold: formatMillionsEur(CSRD_RULES.nonEuTurnoverEur, ctx),
    }
    if (input.euTurnoverEur > CSRD_RULES.nonEuTurnoverEur) {
      return {
        ...base,
        status: 'conditional',
        headline: t('ambito.rules.csrd.nonEuOverHeadline'),
        from: SCOPE_DATES.omnibusInForce,
        fromLabel,
        reasons: [t('ambito.rules.csrd.nonEuOverReason1', amounts), t('ambito.rules.csrd.nonEuOverReason2')],
        notes: csrdNotes(input, ctx),
      }
    }
    return {
      ...base,
      status: 'out_of_scope',
      headline: t('ambito.rules.csrd.nonEuUnderHeadline'),
      reasons: [t('ambito.rules.csrd.nonEuUnderReason1', amounts), t('ambito.rules.csrd.nonEuUnderReason2')],
      notes: csrdNotes(input, ctx),
    }
  }

  if (input.employees == null || input.turnoverEur == null) {
    return { ...base, status: 'not_assessed', headline: t('ambito.rules.csrd.missing'), reasons: [], notes: [] }
  }

  const employees = input.employees
  const turnover = input.turnoverEur
  const empOver = employees > CSRD_RULES.employees
  const revOver = turnover > CSRD_RULES.turnoverEur
  const band = classifyCsrd(employees, turnover, input.listedEu)
  const axis = [
    t('ambito.rules.csrd.axisEmployees', {
      count: formatInt(employees, locale),
      over: empOver ? 'yes' : 'no',
      threshold: formatInt(CSRD_RULES.employees, locale),
    }),
    t('ambito.rules.csrd.axisTurnover', {
      amount: formatMillionsEur(turnover, ctx),
      over: revOver ? 'yes' : 'no',
      threshold: formatMillionsEur(CSRD_RULES.turnoverEur, ctx),
    }),
  ]

  if (band === 'in') {
    return {
      ...base,
      status: 'in_scope',
      headline: t('ambito.rules.csrd.inHeadline'),
      from: SCOPE_DATES.omnibusInForce,
      fromLabel,
      reasons: [t('ambito.rules.csrd.inReason'), ...axis],
      notes: [t('ambito.rules.csrd.inNote1'), t('ambito.rules.csrd.inNote2'), ...csrdNotes(input, ctx)],
    }
  }

  if (band === 'filo') {
    const nearMargin =
      (employees >= CSRD_RULES.employeesMargin.min && employees <= CSRD_RULES.employeesMargin.max) ||
      (turnover >= CSRD_RULES.turnoverMarginEur.min && turnover <= CSRD_RULES.turnoverMarginEur.max)
    const reason =
      empOver && !revOver
        ? t('ambito.rules.csrd.borderEmployees')
        : revOver && !empOver
          ? t('ambito.rules.csrd.borderTurnover')
          : input.listedEu && !nearMargin
            ? t('ambito.rules.csrd.borderListed')
            : t('ambito.rules.csrd.borderMargin')
    return {
      ...base,
      status: 'conditional',
      headline: t('ambito.rules.csrd.borderHeadline'),
      from: SCOPE_DATES.omnibusInForce,
      fromLabel,
      reasons: [reason, ...axis, t('ambito.rules.csrd.borderCheck')],
      notes: [t('ambito.rules.csrd.borderNote1'), t('ambito.rules.csrd.borderNote2'), ...csrdNotes(input, ctx)],
    }
  }

  return {
    ...base,
    status: 'out_of_scope',
    headline: t('ambito.rules.csrd.outHeadline'),
    reasons: [t('ambito.rules.csrd.outReason'), ...axis],
    notes: [
      t('ambito.rules.csrd.outNote1'),
      t('ambito.rules.csrd.outNote2'),
      t('ambito.rules.csrd.outNote3'),
      ...csrdNotes(input, ctx),
    ],
  }
}

function assessCsddd(input: ScopeInput, ctx: TextContext, S: ReturnType<typeof scopeSources>): ScopeResult {
  const { t, locale } = ctx
  const base = {
    framework: 'CSDDD' as const,
    sources: withIndex([S.csddd, S.omnibusI, S.codex]),
    passages: [] as LegalPassage[],
    verifiedOn: VERIFIED_ON,
  }

  if (input.nonEu) {
    return { ...base, status: 'not_assessed', headline: t('ambito.rules.csddd.nonEu'), reasons: [], notes: [] }
  }
  if (input.employees == null || input.turnoverEur == null) {
    return { ...base, status: 'not_assessed', headline: t('ambito.rules.csddd.missing'), reasons: [], notes: [] }
  }

  const empOver = input.employees > CSDDD_RULES.employees
  const revOver = input.turnoverEur > CSDDD_RULES.turnoverEur
  const axis = [
    t('ambito.rules.csrd.axisEmployees', {
      count: formatInt(input.employees, locale),
      over: empOver ? 'yes' : 'no',
      threshold: formatInt(CSDDD_RULES.employees, locale),
    }),
    t('ambito.rules.csrd.axisTurnover', {
      amount: formatMillionsEur(input.turnoverEur, ctx),
      over: revOver ? 'yes' : 'no',
      threshold: formatMillionsEur(CSDDD_RULES.turnoverEur, ctx),
    }),
  ]
  const calendar = t('ambito.rules.csddd.calendar', {
    transposition: formatDate(SCOPE_DATES.csdddTransposition, ctx),
    firstCompliance: formatDate(SCOPE_DATES.csdddFirstCompliance, ctx),
  })

  if (empOver && revOver) {
    return {
      ...base,
      status: 'in_scope',
      headline: t('ambito.rules.csddd.inHeadline'),
      from: SCOPE_DATES.csdddFirstCompliance,
      fromLabel: t('ambito.rules.csddd.inFromLabel', { date: formatDate(SCOPE_DATES.csdddFirstCompliance, ctx) }),
      reasons: [t('ambito.rules.csddd.inReason'), ...axis, calendar],
      notes: [t('ambito.rules.csddd.inNote1'), t('ambito.rules.csddd.inNote2')],
    }
  }

  const which = empOver || revOver ? t('ambito.rules.csddd.outReasonOne') : t('ambito.rules.csddd.outReasonNone')
  return {
    ...base,
    status: 'out_of_scope',
    headline: t('ambito.rules.csddd.outHeadline'),
    reasons: [which, ...axis, calendar],
    notes: [t('ambito.rules.csddd.outNote')],
  }
}

/** The article 50 passage as the landing page cites it from the official Italian text. */
function art50Passage(ctx: TextContext): LegalPassage {
  return {
    before: AI_ACT_ART_50_1_IT.before,
    quote: AI_ACT_ART_50_1_IT.quote,
    after: AI_ACT_ART_50_1_IT.after,
    lang: AI_ACT_ART_50_1_IT.lang,
    act: ctx.t('ui.acts.AI_ACT'),
    article: ctx.t('ambito.rules.obligations.chat.article'),
    celex: AI_ACT_ART_50_1_IT.celex,
    url: eurlexUrl(AI_ACT_ART_50_1_IT.celex, eurlexLang(ctx.locale)),
  }
}

export const AI_KEYS: AiKey[] = ['chat', 'gen', 'emo', 'deep']

const AI_WHO: Record<AiKey, AiObligation['who']> = { chat: 'provider', gen: 'provider', emo: 'deployer', deep: 'deployer' }
const AI_SOURCE: Record<AiKey, 'aiAct50_1' | 'aiAct50_2' | 'aiAct50_3' | 'aiAct50_4'> = {
  chat: 'aiAct50_1',
  gen: 'aiAct50_2',
  emo: 'aiAct50_3',
  deep: 'aiAct50_4',
}

/** Port of OBS in public/scope-aiact.html, in the words of the interface. */
export function aiObligations(ctx: TextContext, S: ReturnType<typeof scopeSources> = scopeSources(ctx)): Record<AiKey, AiObligation> {
  const out = {} as Record<AiKey, AiObligation>
  for (const key of AI_KEYS) {
    out[key] = {
      key,
      who: AI_WHO[key],
      whoLabel: ctx.t(`ambito.results.who.${AI_WHO[key]}`),
      title: ctx.t(`ambito.rules.obligations.${key}.title`),
      requirement: ctx.t(`ambito.rules.obligations.${key}.requirement`),
      exception: ctx.t(`ambito.rules.obligations.${key}.exception`),
      article: ctx.t(`ambito.rules.obligations.${key}.article`),
      source: S[AI_SOURCE[key]],
    }
  }
  return out
}

export function selectedAiKeys(ai: AiActAnswers): AiKey[] {
  return AI_KEYS.filter((k) => ai[AI_KEY_FIELD[k]])
}

function assessAiAct(input: ScopeInput, ctx: TextContext, S: ReturnType<typeof scopeSources>): ScopeResult {
  const { t } = ctx
  const base = {
    framework: 'AI_ACT' as const,
    verifiedOn: VERIFIED_ON,
  }

  if (input.ai == null) {
    return {
      ...base,
      status: 'not_assessed',
      headline: t('ambito.rules.aiAct.notAnswered'),
      reasons: [],
      notes: [],
      sources: withIndex([S.aiAct50_1, S.aiAct113]),
      passages: [],
    }
  }

  const keys = selectedAiKeys(input.ai)

  if (keys.length === 0) {
    return {
      ...base,
      status: 'out_of_scope',
      headline: t('ambito.rules.aiAct.noneHeadline'),
      reasons: [t('ambito.rules.aiAct.noneReason')],
      notes: [
        t('ambito.rules.aiAct.noneNote1', { date: formatDate(SCOPE_DATES.aiActArt4And5, ctx) }),
        t('ambito.rules.aiAct.noneNote2', { date: formatDate(SCOPE_DATES.aiActArt4And5, ctx) }),
        t('ambito.rules.aiAct.noneNote3', { date: formatDate(SCOPE_DATES.aiActGpai, ctx) }),
        t('ambito.rules.aiAct.noneNote4', {
          annexIII: formatDate(SCOPE_DATES.aiActHighRiskAnnexIII, ctx),
          annexI: formatDate(SCOPE_DATES.aiActHighRiskAnnexI, ctx),
        }),
      ],
      sources: withIndex([S.aiAct4, S.aiAct5, S.aiActGpai, S.aiActHighRisk, S.aiAct113]),
      passages: [],
    }
  }

  const all = aiObligations(ctx, S)
  const obligations = keys.map((k) => all[k])
  const sources: Source[] = withIndex([
    ...obligations.map((o) => o.source),
    S.aiAct50_5,
    S.aiAct113,
    S.aiAct99,
    S.legge132,
  ])
  const applies = formatDate(SCOPE_DATES.aiActArt50, ctx)

  return {
    ...base,
    status: 'in_scope',
    headline: t('ambito.rules.aiAct.inHeadline', { date: applies }),
    from: SCOPE_DATES.aiActArt50,
    fromLabel: t('ambito.rules.aiAct.inFromLabel', { date: applies }),
    reasons: [
      ...obligations.map((o) => t('ambito.rules.aiAct.inObligation', { who: o.whoLabel, title: o.title, article: o.article })),
      t('ambito.rules.aiAct.inReason1'),
      t('ambito.rules.aiAct.inReason2'),
    ],
    notes: [
      t('ambito.rules.aiAct.inNote1'),
      t('ambito.rules.aiAct.inNote2'),
      t('ambito.rules.aiAct.inNote3', { date: formatDate(SCOPE_DATES.aiActHighRiskAnnexIII, ctx) }),
    ],
    sources,
    passages: keys.includes('chat') ? [art50Passage(ctx)] : [],
    obligations,
  }
}

export function assessScope(input: ScopeInput, ctx: TextContext): ScopeAssessment {
  const S = scopeSources(ctx)
  return {
    input,
    results: [assessCsrd(input, ctx, S), assessCsddd(input, ctx, S), assessAiAct(input, ctx, S)],
    verifiedOn: VERIFIED_ON,
  }
}
