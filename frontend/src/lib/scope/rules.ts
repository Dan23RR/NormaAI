/**
 * Deterministic scope rules: a first indicative filter, not legal advice.
 *
 * Six rule sets: CSRD, CSDDD, AI Act article 50, AI used by an employer with
 * its workers (D.Lgs. 179/2026, Law 132/2025, AI Act), the Italian NIS decree
 * (D.Lgs. 138/2024) and the Machinery Regulation ((EU) 2023/1230).
 *
 * Every threshold, date and duty a rule states is carried by a provision of
 * the registry in src/lib/verification (RULE_SOURCES below), which
 * scripts/verify_site_sources.py checks word for word on the official text.
 * A rule cites only registry sources; the tests fail when one is missing
 * from the outcomes of that script. Size bands such as "close to a
 * threshold" are a convenience of this tool and are worded as such. The
 * words of every verdict live in the `ambito.rules` messages: this module
 * decides, the messages speak.
 */
import { formatDate, formatInt, formatMillionsEur } from '@/i18n/format'
import type { TextContext } from '@/i18n/types'
import type { Source } from '@/lib/sources'
import { scopeSource, scopeSources } from './sources'
import type {
  AiActAnswers,
  AiKey,
  AiObligation,
  MachineryAnswers,
  MachineryKey,
  NisAnswers,
  NisSector,
  ScopeAssessment,
  ScopeFramework,
  ScopeInput,
  ScopeObligation,
  ScopeResult,
  WorkAiAnswers,
  WorkKey,
} from './types'
import { AI_KEY_FIELD, MACHINERY_KEY_FIELD, NIS_ANNEX_I, NIS_ANNEX_II, WORK_KEY_FIELD } from './types'

/** The provisions the rules rely on, by what each one carries: ids of src/lib/verification/sources.json. */
export const RULE_SOURCES = {
  csrdThresholds: 'dir-2013-34-19bis-1',
  csrdGroup: 'dir-2013-34-29bis-1',
  csrdProtected: 'dir-2013-34-19bis-3-protetta',
  csrdProtectedRight: 'dir-2013-34-19bis-3-rifiuto',
  csrdThirdCountryUnion: 'dir-2013-34-40bis-1-ue',
  csrdThirdCountrySubsidiary: 'dir-2013-34-40bis-1-figlia',
  csrdFirstYear: 'csrd-5-2-b',
  csrdAlreadyReporting: 'csrd-5-2-a',
  csrdMemberStateExemption: 'csrd-5-2-esenzione',
  csrdItalyFirstYear: 'dlgs-125-2024-17-1-b',
  csrdItalyExemption: 'dlgs-125-2024-17-3bis',

  csdddThresholds: 'csddd-2-1-a',
  csdddThirdCountry: 'csddd-2-2-a',
  csdddTwoYears: 'csddd-2-5',
  csdddPartners: 'csddd-8-2bis-a',
  csdddGuidelines: 'csddd-19-3',
  csdddPenalties: 'csddd-27-4',
  csdddTransposition: 'csddd-37-1-recepimento',
  csdddApplication: 'csddd-37-1-applicazione',

  aiLiteracy: 'ai-act-4-1',
  aiEmotionsAtWork: 'ai-act-5-1-f',
  aiWorkplaceNotice: 'ai-act-26-7',
  aiAnnexIIIEmployment: 'ai-act-annex-iii-4',
  ai50_1: 'ai-act-50-1',
  ai50_2: 'ai-act-50-2',
  ai50_3: 'ai-act-50-3',
  ai50_4: 'ai-act-50-4',
  ai50_5: 'ai-act-50-5',
  aiGpai: 'ai-act-53-1',
  aiPenalties: 'ai-act-99-4',
  aiPenaltiesSme: 'ai-act-99-6',
  aiLegacyMarking: 'ai-act-111-4',
  aiApplication: 'ai-act-113-general',
  aiApplicationChapters: 'ai-act-113-a',
  aiApplicationGpai: 'ai-act-113-b',
  aiHighRiskAnnexIII: 'ai-act-113-c-i',
  aiHighRiskAnnexI: 'ai-act-113-c-ii',
  italyAiAuthorities: 'legge-132-2025-20-1',

  workDecisions: 'dlgs-179-2026-41-1',
  workSelection: 'dlgs-179-2026-41-1-selezione',
  workInformation: 'dlgs-179-2026-41-3',
  workNullity: 'dlgs-179-2026-41-4',
  workRiskAssessment: 'dlgs-179-2026-42-2',
  workTraining: 'dlgs-179-2026-42-3',
  workLaw132: 'legge-132-2025-11-2',
  workNotice: 'dlgs-152-1997-1bis-1',
  workNoticeUnions: 'dlgs-152-1997-1bis-6',
  professionalSupport: 'legge-132-2025-13-1',
  professionalInformation: 'legge-132-2025-13-2',

  nisSize: 'dlgs-138-2024-3-2',
  nisSmallCeiling: 'rec-2003-361-2-2',
  nisMediumCeiling: 'rec-2003-361-2-1',
  nisGroup: 'dlgs-138-2024-3-4',
  nisGroupData: 'rec-2003-361-6-2',
  nisAnySize: 'dlgs-138-2024-3-5',
  nisPublic: 'dlgs-138-2024-3-6',
  nisAnnexIVRule: 'dlgs-138-2024-3-8',
  nisDesignated: 'dlgs-138-2024-3-9',
  nisLinked: 'dlgs-138-2024-3-10',
  nisDesignationNotice: 'dlgs-138-2024-3-13',
  nisFinancial: 'dlgs-138-2024-3-14',
  nisEssential: 'dlgs-138-2024-6-1',
  nisImportant: 'dlgs-138-2024-6-3',
  nisRegistration: 'dlgs-138-2024-7-1',
  nisListing: 'dlgs-138-2024-7-3',
  nisUpdate: 'dlgs-138-2024-7-4',
  nisGovernance: 'dlgs-138-2024-23-1',
  nisMeasures: 'dlgs-138-2024-24-1',
  nisSupplyChain: 'dlgs-138-2024-24-2-d',
  nisIncidents: 'dlgs-138-2024-25-5',
  nisPenalties: 'dlgs-138-2024-38-9',
  nisAnnexI: 'dlgs-138-2024-allegato-1',
  nisAnnexII: 'dlgs-138-2024-allegato-2',
  nisAnnexIIManufacturing: 'dlgs-138-2024-allegato-2-fabbricazione',
  nisAnnexIII: 'dlgs-138-2024-allegato-3',
  nisAnnexIV: 'dlgs-138-2024-allegato-4',
  nisMeasures2026: 'acn-det-127434-2026-1-1',
  nisIncidents2026: 'acn-det-127434-2026-1-2',
  nisMeasures2025: 'acn-det-379907-2025-3-1',
  nisIncidents2025: 'acn-det-379907-2025-3-2',

  machineryScope: 'mach-2-1',
  machineryModification: 'mach-3-16',
  machineryManufacturerDef: 'mach-3-18',
  machineryImporterDef: 'mach-3-20',
  machineryDistributorDef: 'mach-3-21',
  machineryRequirements: 'mach-10-1',
  machineryConformity: 'mach-10-2',
  machineryRecords: 'mach-10-3',
  machineryInstructions: 'mach-10-7',
  machineryPartlyCompleted: 'mach-11-2',
  machineryImporter: 'mach-13-1',
  machineryImporterChecks: 'mach-13-2',
  machineryImporterRecords: 'mach-13-8',
  machineryDistributor: 'mach-15-1',
  machineryDistributorChecks: 'mach-15-2',
  machineryOwnBrand: 'mach-17',
  machineryModifier: 'mach-18',
  machineryTransition: 'mach-52-1',
  machineryApplication: 'mach-54',
} as const

export type RuleSourceKey = keyof typeof RULE_SOURCES
const R = RULE_SOURCES

export const CSRD_RULES = {
  employees: 1000,
  turnoverEur: 450_000_000,
  /** Bands "close to a threshold": a convenience of this tool, not a rule of law. */
  employeesMargin: { min: 850, max: 1200 },
  turnoverMarginEur: { min: 380_000_000, max: 550_000_000 },
  nonEuTurnoverEur: 450_000_000,
  nonEuSubsidiaryTurnoverEur: 200_000_000,
} as const

export const CSDDD_RULES = {
  employees: 5000,
  turnoverEur: 1_500_000_000,
  nonEuTurnoverEur: 1_500_000_000,
} as const

/** Ceilings of Recommendation 2003/361/EC, annex, Art. 2, which the NIS decree refers to. */
export const NIS_RULES = {
  small: { employees: 50, turnoverEur: 10_000_000, balanceSheetEur: 10_000_000 },
  medium: { employees: 250, turnoverEur: 50_000_000, balanceSheetEur: 43_000_000 },
} as const

/** Dates the rules state, each with the registry source whose text carries it. */
export const SCOPE_DATES = {
  csrdFirstYear: '2027-01-01',
  csdddTransposition: '2028-07-26',
  csdddFirstCompliance: '2029-07-26',
  csdddGuidelines: '2027-07-26',
  aiActArt4And5: '2025-02-02',
  aiActGpai: '2025-08-02',
  aiActArt50: '2026-08-02',
  aiActLegacyMarking: '2026-12-02',
  aiActNewProhibitions: '2026-12-02',
  aiActHighRiskAnnexIII: '2027-12-02',
  aiActHighRiskAnnexI: '2028-08-02',
  workDecreeInForce: '2026-10-23',
  nisIncidents2026: '2027-01-01',
  nisMeasures2026: '2027-07-31',
  machineryApplication: '2027-01-20',
} as const

export const SCOPE_DATE_SOURCES: Record<keyof typeof SCOPE_DATES, RuleSourceKey> = {
  csrdFirstYear: 'csrdFirstYear',
  csdddTransposition: 'csdddTransposition',
  csdddFirstCompliance: 'csdddApplication',
  csdddGuidelines: 'csdddGuidelines',
  aiActArt4And5: 'aiApplicationChapters',
  aiActGpai: 'aiApplicationGpai',
  aiActArt50: 'aiApplication',
  aiActLegacyMarking: 'aiLegacyMarking',
  aiActNewProhibitions: 'aiApplicationChapters',
  aiActHighRiskAnnexIII: 'aiHighRiskAnnexIII',
  aiActHighRiskAnnexI: 'aiHighRiskAnnexI',
  workDecreeInForce: 'workDecisions',
  nisIncidents2026: 'nisIncidents2026',
  nisMeasures2026: 'nisMeasures2026',
  machineryApplication: 'machineryApplication',
}

type Keys = RuleSourceKey[]

function sourcesOf(keys: Keys, ctx: TextContext): Source[] {
  return scopeSources(
    keys.map((k) => R[k]),
    ctx,
  )
}

function notAssessed(framework: ScopeFramework, headline: string, keys: Keys, ctx: TextContext): ScopeResult {
  return { framework, status: 'not_assessed', headline, reasons: [], notes: [], sources: sourcesOf(keys, ctx) }
}

// ─── CSRD ────────────────────────────────────────────────────────────

export type CsrdBand = 'in' | 'filo' | 'out'

/** In scope above both thresholds; "filo" above one, close to one, or listed below them. */
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

function csrdNotes(input: ScopeInput, ctx: TextContext): { notes: string[]; keys: Keys } {
  const notes: string[] = []
  const keys: Keys = []
  if (input.wave1Reporter) {
    notes.push(ctx.t('ambito.rules.csrd.noteWave1'))
    keys.push('csrdAlreadyReporting', 'csrdItalyExemption', 'csrdMemberStateExemption')
  }
  if (input.groupRole === 'parent') {
    notes.push(ctx.t('ambito.rules.csrd.noteParent'))
    keys.push('csrdGroup')
  }
  if (input.groupRole === 'subsidiary') notes.push(ctx.t('ambito.rules.csrd.noteSubsidiary'))
  return { notes, keys }
}

function assessCsrd(input: ScopeInput, ctx: TextContext): ScopeResult {
  const { t, locale } = ctx
  const framework = 'CSRD' as const
  const firstYear = formatDate(SCOPE_DATES.csrdFirstYear, ctx)
  const fromLabel = t('ambito.rules.csrd.fromLabel', { date: firstYear })
  const extra = csrdNotes(input, ctx)

  if (input.nonEu) {
    const keys: Keys = ['csrdThirdCountryUnion', 'csrdThirdCountrySubsidiary']
    if (input.euTurnoverEur == null) return notAssessed(framework, t('ambito.rules.csrd.nonEuMissing'), keys, ctx)
    const amounts = {
      amount: formatMillionsEur(input.euTurnoverEur, ctx),
      threshold: formatMillionsEur(CSRD_RULES.nonEuTurnoverEur, ctx),
    }
    if (input.euTurnoverEur > CSRD_RULES.nonEuTurnoverEur) {
      return {
        framework,
        status: 'conditional',
        headline: t('ambito.rules.csrd.nonEuOverHeadline'),
        reasons: [
          t('ambito.rules.csrd.nonEuOverReason1', amounts),
          t('ambito.rules.csrd.nonEuOverReason2', {
            threshold: formatMillionsEur(CSRD_RULES.nonEuSubsidiaryTurnoverEur, ctx),
          }),
        ],
        notes: extra.notes,
        sources: sourcesOf([...keys, ...extra.keys], ctx),
      }
    }
    return {
      framework,
      status: 'out_of_scope',
      headline: t('ambito.rules.csrd.nonEuUnderHeadline'),
      reasons: [t('ambito.rules.csrd.nonEuUnderReason1', amounts), t('ambito.rules.csrd.nonEuUnderReason2')],
      notes: extra.notes,
      sources: sourcesOf([...keys, 'csrdThresholds', ...extra.keys], ctx),
    }
  }

  if (input.employees == null || input.turnoverEur == null) {
    return notAssessed(framework, t('ambito.rules.csrd.missing'), ['csrdThresholds'], ctx)
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
      framework,
      status: 'in_scope',
      headline: t('ambito.rules.csrd.inHeadline'),
      from: SCOPE_DATES.csrdFirstYear,
      fromLabel,
      reasons: [t('ambito.rules.csrd.inReason'), ...axis],
      notes: [t('ambito.rules.csrd.inNote1', { date: firstYear }), ...extra.notes],
      sources: sourcesOf(['csrdThresholds', 'csrdFirstYear', 'csrdItalyFirstYear', ...extra.keys], ctx),
    }
  }

  const supplyChain = t('ambito.rules.csrd.noteProtected', { threshold: formatInt(CSRD_RULES.employees, locale) })
  const exemption = t('ambito.rules.csrd.noteItalyExemption')

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
      framework,
      status: 'conditional',
      headline: t('ambito.rules.csrd.borderHeadline'),
      reasons: [reason, ...axis, t('ambito.rules.csrd.borderCheck')],
      notes: [t('ambito.rules.csrd.borderNote1'), exemption, ...(empOver ? [] : [supplyChain]), ...extra.notes],
      sources: sourcesOf(
        [
          'csrdThresholds',
          'csrdFirstYear',
          'csrdItalyExemption',
          ...(empOver ? [] : (['csrdProtected', 'csrdProtectedRight'] as Keys)),
          ...extra.keys,
        ],
        ctx,
      ),
    }
  }

  return {
    framework,
    status: 'out_of_scope',
    headline: t('ambito.rules.csrd.outHeadline'),
    reasons: [t('ambito.rules.csrd.outReason'), ...axis],
    notes: [exemption, supplyChain, ...extra.notes],
    sources: sourcesOf(['csrdThresholds', 'csrdItalyExemption', 'csrdProtected', 'csrdProtectedRight', ...extra.keys], ctx),
  }
}

// ─── CSDDD ───────────────────────────────────────────────────────────

function assessCsddd(input: ScopeInput, ctx: TextContext): ScopeResult {
  const { t, locale } = ctx
  const framework = 'CSDDD' as const
  const firstCompliance = formatDate(SCOPE_DATES.csdddFirstCompliance, ctx)
  const calendar = t('ambito.rules.csddd.calendar', {
    transposition: formatDate(SCOPE_DATES.csdddTransposition, ctx),
    firstCompliance,
  })
  const inNotes = [
    t('ambito.rules.csddd.inNote1'),
    t('ambito.rules.csddd.inNote2'),
    t('ambito.rules.csddd.inNote3', { date: formatDate(SCOPE_DATES.csdddGuidelines, ctx) }),
  ]
  const dates: Keys = ['csdddTransposition', 'csdddApplication']
  const inKeys: Keys = ['csdddTwoYears', 'csdddPenalties', 'csdddGuidelines']
  const fromLabel = t('ambito.rules.csddd.inFromLabel', { date: firstCompliance })

  if (input.nonEu) {
    if (input.euTurnoverEur == null) {
      return notAssessed(framework, t('ambito.rules.csddd.nonEuMissing'), ['csdddThirdCountry'], ctx)
    }
    const amounts = {
      amount: formatMillionsEur(input.euTurnoverEur, ctx),
      threshold: formatMillionsEur(CSDDD_RULES.nonEuTurnoverEur, ctx),
    }
    if (input.euTurnoverEur > CSDDD_RULES.nonEuTurnoverEur) {
      return {
        framework,
        status: 'in_scope',
        headline: t('ambito.rules.csddd.nonEuInHeadline'),
        from: SCOPE_DATES.csdddFirstCompliance,
        fromLabel,
        reasons: [t('ambito.rules.csddd.nonEuInReason', amounts), calendar],
        notes: inNotes,
        sources: sourcesOf(['csdddThirdCountry', ...dates, ...inKeys], ctx),
      }
    }
    return {
      framework,
      status: 'out_of_scope',
      headline: t('ambito.rules.csddd.outHeadline'),
      reasons: [t('ambito.rules.csddd.nonEuOutReason', amounts), calendar],
      notes: [t('ambito.rules.csddd.outNote', { threshold: formatInt(CSDDD_RULES.employees, locale) })],
      sources: sourcesOf(['csdddThirdCountry', ...dates, 'csdddPartners'], ctx),
    }
  }

  if (input.employees == null || input.turnoverEur == null) {
    return notAssessed(framework, t('ambito.rules.csddd.missing'), ['csdddThresholds'], ctx)
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

  if (empOver && revOver) {
    return {
      framework,
      status: 'in_scope',
      headline: t('ambito.rules.csddd.inHeadline'),
      from: SCOPE_DATES.csdddFirstCompliance,
      fromLabel,
      reasons: [t('ambito.rules.csddd.inReason'), ...axis, calendar],
      notes: inNotes,
      sources: sourcesOf(['csdddThresholds', ...dates, ...inKeys], ctx),
    }
  }

  const which = empOver || revOver ? t('ambito.rules.csddd.outReasonOne') : t('ambito.rules.csddd.outReasonNone')
  return {
    framework,
    status: 'out_of_scope',
    headline: t('ambito.rules.csddd.outHeadline'),
    reasons: [which, ...axis, calendar],
    notes: [t('ambito.rules.csddd.outNote', { threshold: formatInt(CSDDD_RULES.employees, locale) })],
    sources: sourcesOf(['csdddThresholds', ...dates, 'csdddPartners'], ctx),
  }
}

// ─── AI Act, article 50 ──────────────────────────────────────────────

export const AI_KEYS: AiKey[] = ['chat', 'gen', 'emo', 'deep']

const AI_WHO: Record<AiKey, AiObligation['who']> = { chat: 'provider', gen: 'provider', emo: 'deployer', deep: 'deployer' }
const AI_SOURCE: Record<AiKey, RuleSourceKey> = { chat: 'ai50_1', gen: 'ai50_2', emo: 'ai50_3', deep: 'ai50_4' }
/** What each exception text also relies on. */
const AI_EXTRA: Record<AiKey, Keys> = { chat: [], gen: ['aiLegacyMarking'], emo: ['aiEmotionsAtWork'], deep: [] }

/** The four Article 50 obligations, in the words of the interface. */
export function aiObligations(ctx: TextContext): Record<AiKey, AiObligation> {
  const out = {} as Record<AiKey, AiObligation>
  for (const key of AI_KEYS) {
    const source = scopeSource(R[AI_SOURCE[key]], ctx)
    out[key] = {
      key,
      who: AI_WHO[key],
      whoLabel: ctx.t(`ambito.results.who.${AI_WHO[key]}`),
      title: ctx.t(`ambito.rules.obligations.${key}.title`),
      requirement: ctx.t(`ambito.rules.obligations.${key}.requirement`),
      exception: ctx.t(`ambito.rules.obligations.${key}.exception`, {
        legacy: formatDate(SCOPE_DATES.aiActLegacyMarking, ctx),
        applies: formatDate(SCOPE_DATES.aiActArt50, ctx),
        prohibitions: formatDate(SCOPE_DATES.aiActArt4And5, ctx),
      }),
      article: source.article ?? '',
      source,
    }
  }
  return out
}

export function selectedAiKeys(ai: AiActAnswers): AiKey[] {
  return AI_KEYS.filter((k) => ai[AI_KEY_FIELD[k]])
}

function assessAiAct(input: ScopeInput, ctx: TextContext): ScopeResult {
  const { t } = ctx
  const framework = 'AI_ACT' as const

  if (input.ai == null) {
    return notAssessed(framework, t('ambito.rules.aiAct.notAnswered'), ['ai50_1', 'aiApplication'], ctx)
  }

  const keys = selectedAiKeys(input.ai)
  const annexIII = formatDate(SCOPE_DATES.aiActHighRiskAnnexIII, ctx)

  if (keys.length === 0) {
    return {
      framework,
      status: 'out_of_scope',
      headline: t('ambito.rules.aiAct.noneHeadline'),
      reasons: [t('ambito.rules.aiAct.noneReason')],
      notes: [
        t('ambito.rules.aiAct.noneNote1', { date: formatDate(SCOPE_DATES.aiActArt4And5, ctx) }),
        t('ambito.rules.aiAct.noneNote2', {
          date: formatDate(SCOPE_DATES.aiActArt4And5, ctx),
          added: formatDate(SCOPE_DATES.aiActNewProhibitions, ctx),
        }),
        t('ambito.rules.aiAct.noneNote3', { date: formatDate(SCOPE_DATES.aiActGpai, ctx) }),
        t('ambito.rules.aiAct.noneNote4', { annexIII, annexI: formatDate(SCOPE_DATES.aiActHighRiskAnnexI, ctx) }),
      ],
      sources: sourcesOf(
        [
          'aiLiteracy',
          'aiApplicationChapters',
          'aiEmotionsAtWork',
          'aiGpai',
          'aiApplicationGpai',
          'aiHighRiskAnnexIII',
          'aiHighRiskAnnexI',
        ],
        ctx,
      ),
    }
  }

  const all = aiObligations(ctx)
  const obligations = keys.map((k) => all[k])
  const applies = formatDate(SCOPE_DATES.aiActArt50, ctx)

  return {
    framework,
    status: 'in_scope',
    headline: t('ambito.rules.aiAct.inHeadline', { date: applies }),
    from: SCOPE_DATES.aiActArt50,
    fromLabel: t('ambito.rules.aiAct.inFromLabel', { date: applies }),
    reasons: [
      ...obligations.map((o) => t('ambito.rules.shared.obligation', { who: o.whoLabel, title: o.title, article: o.article })),
      t('ambito.rules.aiAct.inReason1'),
      t('ambito.rules.aiAct.inReason2'),
    ],
    notes: [
      t('ambito.rules.aiAct.inNote1'),
      t('ambito.rules.aiAct.inNote2'),
      t('ambito.rules.aiAct.inNote3', { date: annexIII }),
    ],
    sources: sourcesOf(
      [
        ...keys.map((k) => AI_SOURCE[k]),
        ...keys.flatMap((k) => AI_EXTRA[k]),
        'ai50_5',
        'aiApplication',
        'aiPenalties',
        'aiPenaltiesSme',
        'italyAiAuthorities',
        'aiHighRiskAnnexIII',
      ],
      ctx,
    ),
    obligations,
  }
}

// ─── AI used by an employer with its workers ─────────────────────────

export const WORK_KEYS: WorkKey[] = ['dec', 'org', 'uso', 'prof', 'emo']

export function selectedWorkKeys(work: WorkAiAnswers): WorkKey[] {
  return WORK_KEYS.filter((k) => work[WORK_KEY_FIELD[k]])
}

interface Duty {
  key: string
  who: string
  source: RuleSourceKey
  /** Other provisions the wording of the duty relies on. */
  also?: Keys
  values?: Record<string, string>
}

function obligationOf(set: string, duty: Duty, ctx: TextContext): ScopeObligation {
  const base = `ambito.rules.${set}.duties.${duty.key}`
  const source = scopeSource(R[duty.source], ctx)
  return {
    key: duty.key,
    who: duty.who,
    whoLabel: ctx.t(`ambito.results.who.${duty.who}`),
    title: ctx.t(`${base}.title`),
    requirement: ctx.t(`${base}.requirement`, duty.values),
    exception: ctx.t.has(`${base}.exception`) ? ctx.t(`${base}.exception`, duty.values) : undefined,
    article: source.article ?? '',
    source,
  }
}

function dutySources(duties: Duty[]): Keys {
  return duties.flatMap((d) => [d.source, ...(d.also ?? [])])
}

function workDuties(keys: WorkKey[], ctx: TextContext): Duty[] {
  const has = (k: WorkKey) => keys.includes(k)
  const duties: Duty[] = []
  if (has('emo')) {
    duties.push({
      key: 'emotions',
      who: 'employer',
      source: 'aiEmotionsAtWork',
      also: ['aiApplicationChapters'],
      values: { date: formatDate(SCOPE_DATES.aiActArt4And5, ctx) },
    })
  }
  if (has('dec')) {
    duties.push(
      { key: 'decisions', who: 'employer', source: 'workDecisions', also: ['workSelection', 'workNullity'] },
      {
        key: 'information',
        who: 'employer',
        source: 'workInformation',
        also: ['workNotice', 'workNoticeUnions', 'workLaw132'],
      },
      {
        key: 'highRisk',
        who: 'employer',
        source: 'aiWorkplaceNotice',
        also: ['aiAnnexIIIEmployment', 'aiHighRiskAnnexIII'],
        values: { date: formatDate(SCOPE_DATES.aiActHighRiskAnnexIII, ctx) },
      },
    )
  }
  if (has('org')) duties.push({ key: 'riskAssessment', who: 'employer', source: 'workRiskAssessment' })
  if (has('org') || has('uso') || has('dec')) duties.push({ key: 'training', who: 'employer', source: 'workTraining' })
  if (has('uso') || has('dec') || has('org') || has('prof')) {
    duties.push({
      key: 'literacy',
      who: 'deployer',
      source: 'aiLiteracy',
      also: ['aiApplicationChapters'],
      values: { date: formatDate(SCOPE_DATES.aiActArt4And5, ctx) },
    })
  }
  if (has('prof')) {
    duties.push({ key: 'clients', who: 'professional', source: 'professionalInformation', also: ['professionalSupport'] })
  }
  return duties
}

function assessWork(input: ScopeInput, ctx: TextContext): ScopeResult {
  const { t } = ctx
  const framework = 'AI_WORK' as const
  if (input.work == null) {
    return notAssessed(framework, t('ambito.rules.work.notAnswered'), ['workDecisions', 'aiLiteracy'], ctx)
  }

  const keys = selectedWorkKeys(input.work)
  if (keys.length === 0) {
    return {
      framework,
      status: 'out_of_scope',
      headline: t('ambito.rules.work.noneHeadline'),
      reasons: [t('ambito.rules.work.noneReason')],
      notes: [t('ambito.rules.work.noneNote')],
      sources: sourcesOf(['workDecisions', 'workRiskAssessment', 'aiLiteracy'], ctx),
    }
  }

  const duties = workDuties(keys, ctx)
  const decree = keys.includes('dec') || keys.includes('org')
  const inForce = formatDate(SCOPE_DATES.workDecreeInForce, ctx)
  return {
    framework,
    status: 'in_scope',
    headline: t(keys.includes('emo') ? 'ambito.rules.work.inHeadlineProhibited' : 'ambito.rules.work.inHeadline'),
    from: decree ? SCOPE_DATES.workDecreeInForce : undefined,
    fromLabel: decree ? t('ambito.rules.work.inFromLabel', { date: inForce }) : undefined,
    reasons: keys.map((k) => t(`ambito.rules.work.reasons.${k}`)),
    notes: [
      ...(keys.includes('dec') ? [t('ambito.rules.work.inNote1')] : []),
      ...(decree ? [t('ambito.rules.work.inNote2')] : []),
    ],
    sources: sourcesOf([...dutySources(duties), ...(decree ? (['workLaw132'] as Keys) : [])], ctx),
    obligations: duties.map((d) => obligationOf('work', d, ctx)),
  }
}

// ─── NIS (D.Lgs. 138/2024) ───────────────────────────────────────────

export type SizeClass = 'small' | 'not_small' | 'unknown'

/**
 * A small enterprise employs fewer than 50 persons and has a turnover or a
 * balance sheet total not above 10 million euro (Recommendation 2003/361/EC,
 * annex, Art. 2(2)). "unknown" when the figures given do not settle it.
 */
export function nisSizeClass(employees: number | null, turnoverEur: number | null, balanceSheetEur: number | null): SizeClass {
  const { small } = NIS_RULES
  if (employees != null && employees >= small.employees) return 'not_small'
  const turnoverWithin = turnoverEur == null ? null : turnoverEur <= small.turnoverEur
  const balanceWithin = balanceSheetEur == null ? null : balanceSheetEur <= small.balanceSheetEur
  if (turnoverWithin === false && balanceWithin === false) return 'not_small'
  if (employees == null) return 'unknown'
  if (turnoverWithin === true || balanceWithin === true) return 'small'
  return 'unknown'
}

export type NisCategory = 'essential' | 'important' | 'depends'

/**
 * Annex I entities above the ceilings for medium-sized enterprises are
 * essential (Art. 6(1)(a)); the others in scope are important (Art. 6(3)).
 * Medium-sized: fewer than 250 persons and turnover not above 50 million
 * euro or balance sheet total not above 43 million euro.
 */
export function nisCategory(
  sector: NisSector,
  employees: number | null,
  turnoverEur: number | null,
  balanceSheetEur: number | null,
): NisCategory {
  if (!(NIS_ANNEX_I as readonly string[]).includes(sector)) return 'important'
  const { medium } = NIS_RULES
  if (employees != null && employees >= medium.employees) return 'essential'
  const turnoverWithin = turnoverEur == null ? null : turnoverEur <= medium.turnoverEur
  const balanceWithin = balanceSheetEur == null ? null : balanceSheetEur <= medium.balanceSheetEur
  if (turnoverWithin === false && balanceWithin === false) return 'essential'
  if (employees != null && (turnoverWithin === true || balanceWithin === true)) return 'important'
  return 'depends'
}

function isAnnexI(sector: NisSector): boolean {
  return (NIS_ANNEX_I as readonly string[]).includes(sector)
}

function isAnnexII(sector: NisSector): boolean {
  return (NIS_ANNEX_II as readonly string[]).includes(sector)
}

function nisDuties(ctx: TextContext, financial: boolean): Duty[] {
  const dates = {
    measures2026: formatDate(SCOPE_DATES.nisMeasures2026, ctx),
    incidents2026: formatDate(SCOPE_DATES.nisIncidents2026, ctx),
  }
  const register: Duty = { key: 'register', who: 'nisEntity', source: 'nisRegistration', also: ['nisListing', 'nisUpdate'] }
  // Banks and financial market infrastructures: chapters IV and V do not apply, DORA does (Art. 3(14)).
  if (financial) return [register]
  return [
    register,
    { key: 'governance', who: 'governingBodies', source: 'nisGovernance' },
    {
      key: 'measures',
      who: 'nisEntity',
      source: 'nisMeasures',
      also: ['nisSupplyChain', 'nisMeasures2026', 'nisMeasures2025'],
      values: dates,
    },
    {
      key: 'incidents',
      who: 'nisEntity',
      source: 'nisIncidents',
      also: ['nisIncidents2026', 'nisIncidents2025'],
      values: dates,
    },
  ]
}

function assessNis(input: ScopeInput, ctx: TextContext): ScopeResult {
  const { t, locale } = ctx
  const framework = 'NIS2' as const
  const nis: NisAnswers | null = input.nis
  if (nis == null) {
    return notAssessed(framework, t('ambito.rules.nis.notAnswered'), ['nisSize', 'nisAnnexI', 'nisAnnexII'], ctx)
  }

  const sector = nis.sector
  const annexI = isAnnexI(sector)
  const annexII = isAnnexII(sector)
  const financial = sector === 'banche' || sector === 'mercati'
  const sectorName = t(`ambito.nis.sectors.${sector}`)
  const annexKey: RuleSourceKey = annexI ? 'nisAnnexI' : 'nisAnnexII'
  const groupNote = input.groupRole === 'standalone' ? [] : [t('ambito.rules.nis.noteGroup')]
  const groupKeys: Keys = input.groupRole === 'standalone' ? [] : ['nisGroup', 'nisGroupData']
  const outNotes = [t('ambito.rules.nis.outNoteDesignated'), t('ambito.rules.nis.outNoteSupplyChain')]
  const outKeys: Keys = ['nisDesignated', 'nisSupplyChain']

  const inScope = (reasons: string[], keys: Keys, category?: NisCategory): ScopeResult => {
    const duties = nisDuties(ctx, financial)
    const categoryNote = category
      ? t(`ambito.rules.nis.category.${category}`)
      : t('ambito.rules.nis.category.byAuthority')
    return {
      framework,
      status: financial ? 'conditional' : 'in_scope',
      headline: t(financial ? 'ambito.rules.nis.financialHeadline' : 'ambito.rules.nis.inHeadline'),
      reasons,
      notes: [
        ...(financial ? [t('ambito.rules.nis.noteFinancial')] : []),
        categoryNote,
        ...(financial ? [] : [t('ambito.rules.nis.notePenalties')]),
        ...groupNote,
      ],
      sources: sourcesOf(
        [
          ...keys,
          ...(financial ? (['nisFinancial'] as Keys) : []),
          'nisEssential',
          'nisImportant',
          ...dutySources(duties),
          ...(financial ? [] : (['nisPenalties'] as Keys)),
          ...groupKeys,
        ],
        ctx,
      ),
      obligations: duties.map((d) => obligationOf('nis', d, ctx)),
    }
  }

  if (nis.linked) return inScope([t('ambito.rules.nis.reasonLinked')], ['nisLinked'])
  if (nis.anySize) return inScope([t('ambito.rules.nis.reasonAnySize')], ['nisAnySize'])
  if (sector === 'pa') return inScope([t('ambito.rules.nis.reasonPublic')], ['nisPublic', 'nisAnnexIII'])

  if (sector === 'altri') {
    return {
      framework,
      status: 'conditional',
      headline: t('ambito.rules.nis.annexIVHeadline'),
      reasons: [t('ambito.rules.nis.annexIVReason')],
      notes: [t('ambito.rules.nis.annexIVNote')],
      sources: sourcesOf(['nisAnnexIVRule', 'nisAnnexIV', 'nisDesignationNotice'], ctx),
    }
  }

  if (!annexI && !annexII) {
    return {
      framework,
      status: 'out_of_scope',
      headline: t('ambito.rules.nis.noSectorHeadline'),
      reasons: [t('ambito.rules.nis.noSectorReason')],
      notes: outNotes,
      sources: sourcesOf(['nisSize', 'nisAnnexI', 'nisAnnexII', ...outKeys], ctx),
    }
  }

  const sectorReason = t(annexI ? 'ambito.rules.nis.reasonAnnexI' : 'ambito.rules.nis.reasonAnnexII', { sector: sectorName })
  const sectorKeys: Keys = [annexKey, ...(sector === 'fabbricazione' ? (['nisAnnexIIManufacturing'] as Keys) : [])]
  const sizeKeys: Keys = ['nisSize', 'nisSmallCeiling']
  const size = nisSizeClass(input.employees, input.turnoverEur, input.balanceSheetEur)
  const ceilings = {
    employees: formatInt(NIS_RULES.small.employees, locale),
    amount: formatMillionsEur(NIS_RULES.small.turnoverEur, ctx),
  }

  if (size === 'not_small') {
    const category = nisCategory(sector, input.employees, input.turnoverEur, input.balanceSheetEur)
    return inScope(
      [sectorReason, t('ambito.rules.nis.reasonNotSmall', ceilings)],
      [...sectorKeys, ...sizeKeys, ...(annexI ? (['nisMediumCeiling'] as Keys) : [])],
      category,
    )
  }

  if (size === 'small') {
    return {
      framework,
      status: 'out_of_scope',
      headline: t('ambito.rules.nis.smallHeadline'),
      reasons: [sectorReason, t('ambito.rules.nis.reasonSmall', ceilings)],
      notes: [...outNotes, ...groupNote],
      sources: sourcesOf([...sectorKeys, ...sizeKeys, ...outKeys, ...groupKeys], ctx),
    }
  }

  // The figures given do not settle the size class.
  const missing =
    input.employees == null
      ? t('ambito.rules.nis.missingEmployees')
      : input.turnoverEur == null && input.balanceSheetEur == null
        ? t('ambito.rules.nis.missingFinancials', ceilings)
        : input.balanceSheetEur == null
          ? t('ambito.rules.nis.missingBalance', ceilings)
          : t('ambito.rules.nis.missingTurnover', ceilings)
  const known = input.employees != null && (input.turnoverEur != null || input.balanceSheetEur != null)
  return {
    framework,
    status: known ? 'conditional' : 'not_assessed',
    headline: known ? t('ambito.rules.nis.sizeDependsHeadline') : missing,
    reasons: known ? [sectorReason, missing] : [],
    notes: known ? groupNote : [],
    sources: sourcesOf([...sectorKeys, ...sizeKeys, ...(known ? groupKeys : [])], ctx),
  }
}

// ─── Machinery Regulation ────────────────────────────────────────────

export const MACHINERY_KEYS: MachineryKey[] = ['fab', 'imp', 'dis', 'mod']

export function selectedMachineryKeys(machinery: MachineryAnswers): MachineryKey[] {
  return MACHINERY_KEYS.filter((k) => machinery[MACHINERY_KEY_FIELD[k]])
}

function machineryDuties(keys: MachineryKey[]): Duty[] {
  const has = (k: MachineryKey) => keys.includes(k)
  const duties: Duty[] = []
  if (has('fab')) {
    duties.push(
      {
        key: 'conformity',
        who: 'manufacturer',
        source: 'machineryRequirements',
        also: ['machineryConformity', 'machineryRecords', 'machineryInstructions'],
      },
      { key: 'partlyCompleted', who: 'manufacturer', source: 'machineryPartlyCompleted' },
    )
  }
  if (has('imp')) {
    duties.push({
      key: 'importer',
      who: 'importer',
      source: 'machineryImporter',
      also: ['machineryImporterChecks', 'machineryImporterRecords'],
    })
  }
  if (has('dis')) {
    duties.push({ key: 'distributor', who: 'distributor', source: 'machineryDistributorChecks', also: ['machineryDistributor'] })
  }
  if (has('imp') || has('dis')) {
    duties.push({ key: 'ownBrand', who: has('imp') ? 'importer' : 'distributor', source: 'machineryOwnBrand' })
  }
  if (has('mod')) {
    duties.push({ key: 'modification', who: 'modifier', source: 'machineryModifier', also: ['machineryModification'] })
  }
  return duties
}

function assessMachinery(input: ScopeInput, ctx: TextContext): ScopeResult {
  const { t } = ctx
  const framework = 'MACHINERY' as const
  if (input.machinery == null) {
    return notAssessed(framework, t('ambito.rules.machinery.notAnswered'), ['machineryScope', 'machineryApplication'], ctx)
  }

  const keys = selectedMachineryKeys(input.machinery)
  const applies = formatDate(SCOPE_DATES.machineryApplication, ctx)
  if (keys.length === 0) {
    return {
      framework,
      status: 'out_of_scope',
      headline: t('ambito.rules.machinery.noneHeadline'),
      reasons: [t('ambito.rules.machinery.noneReason')],
      notes: [t('ambito.rules.machinery.noneNote')],
      sources: sourcesOf(['machineryScope', 'machineryModifier', 'machineryModification'], ctx),
    }
  }

  const duties = machineryDuties(keys)
  const roles: Keys = [
    ...(keys.includes('fab') ? (['machineryManufacturerDef'] as Keys) : []),
    ...(keys.includes('imp') ? (['machineryImporterDef'] as Keys) : []),
    ...(keys.includes('dis') ? (['machineryDistributorDef'] as Keys) : []),
  ]
  return {
    framework,
    status: 'in_scope',
    headline: t('ambito.rules.machinery.inHeadline', { date: applies }),
    from: SCOPE_DATES.machineryApplication,
    fromLabel: t('ambito.rules.machinery.inFromLabel', { date: applies }),
    reasons: keys.map((k) => t(`ambito.rules.machinery.reasons.${k}`)),
    notes: [t('ambito.rules.machinery.inNote1'), t('ambito.rules.machinery.inNote2', { date: applies })],
    sources: sourcesOf(
      ['machineryApplication', 'machineryScope', ...roles, ...dutySources(duties), 'machineryTransition'],
      ctx,
    ),
    obligations: duties.map((d) => obligationOf('machinery', d, ctx)),
  }
}

// ─── The assessment ──────────────────────────────────────────────────

/** The rule sets in the order the results are returned. */
export const SCOPE_FRAMEWORKS: ScopeFramework[] = ['AI_WORK', 'NIS2', 'MACHINERY', 'AI_ACT', 'CSRD', 'CSDDD']

export function assessScope(input: ScopeInput, ctx: TextContext): ScopeAssessment {
  return {
    input,
    results: [
      assessWork(input, ctx),
      assessNis(input, ctx),
      assessMachinery(input, ctx),
      assessAiAct(input, ctx),
      assessCsrd(input, ctx),
      assessCsddd(input, ctx),
    ],
  }
}
