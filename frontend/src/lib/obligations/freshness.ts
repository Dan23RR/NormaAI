/**
 * The automatic check of consolidated versions, as GET /api/v1/stats
 * reports it in `freshness`: when it last ran and which indexed acts have a
 * newer consolidated text in CELLAR. The backend that does not run the check
 * (or the demo) sends no `freshness`: the page then says the calendar is
 * curated by hand and nothing more.
 */
import type { TextContext } from '@/i18n/types'
import { dateWithArticle } from '@/lib/scope/sources'

export interface OutdatedAct {
  celex: string
  indexed: string
  latest: string
}

export interface Freshness {
  /** ISO timestamp of the last run, null when the check never ran. */
  checkedAt: string | null
  outdated: OutdatedAct[]
}

/** The `freshness` object of a stats answer, or undefined when the answer has none (or it is malformed). */
export function readFreshness(stats: unknown): Freshness | undefined {
  const raw = (stats as { freshness?: unknown } | null | undefined)?.freshness
  if (!raw || typeof raw !== 'object') return undefined
  const { checked_at: checkedAt, outdated } = raw as { checked_at?: unknown; outdated?: unknown }
  if (checkedAt != null && typeof checkedAt !== 'string') return undefined
  const list: OutdatedAct[] = []
  for (const item of Array.isArray(outdated) ? outdated : []) {
    if (!item || typeof item !== 'object') continue
    const { celex, indexed, latest } = item as Record<string, unknown>
    if (typeof celex === 'string' && typeof indexed === 'string' && typeof latest === 'string') {
      list.push({ celex, indexed, latest })
    }
  }
  return { checkedAt: typeof checkedAt === 'string' && checkedAt.trim() ? checkedAt : null, outdated: list }
}

/**
 * The header line of Monitoraggio. With a `freshness` that ran: when, and how
 * many indexed acts have a newer consolidated version. Otherwise the honest
 * sentence: the calendar is curated by hand.
 */
export function freshnessLine(freshness: Freshness | undefined, ctx: TextContext): string {
  if (!freshness) return ctx.t('monitoraggio.meta.manual')
  if (!freshness.checkedAt) return ctx.t('monitoraggio.meta.neverRan')
  return ctx.t('monitoraggio.meta.checked', {
    date: dateWithArticle(freshness.checkedAt, ctx),
    count: freshness.outdated.length,
  })
}
