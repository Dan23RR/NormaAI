import type { BadgeTone } from '@/components/ui/Badge'
import { eurlexLang } from '@/i18n/config'
import { formatDate } from '@/i18n/format'
import type { TextContext, Translate } from '@/i18n/types'
import { actOfCelex, isCelex, isUsefulUrl, originOf } from '@/lib/chiedi/sources'
import { eurlexUrl } from '@/lib/sources'
import type { CheckCounts, Dependency, FindingAct, FindingGroup, FindingStatus } from './types'
import { GROUPS } from './types'

/** Each group has a tone and an icon of its own: the colour never carries the meaning alone. */
export const GROUP_TONE: Record<FindingGroup, BadgeTone> = {
  correggere: 'bad',
  controllare: 'warn',
  a_posto: 'ok',
  non_coperto: 'neutral',
}

export const GROUP_TEXT: Record<FindingGroup, string> = {
  correggere: 'text-bad',
  controllare: 'text-warn',
  a_posto: 'text-ok',
  non_coperto: 'text-ink-2',
}

export function groupLabel(group: FindingGroup, t: Translate): string {
  return t(`controlla.groups.${group}.label`)
}

/**
 * The two outcomes a re-check gives: the provision changed, or it is gone,
 * after the check (not after the document's date). The server sends them with
 * codes of their own; older servers reused "cambiato" and "inesistente" and
 * told them apart only by the label, which is still understood.
 */
export const RECHECK_CODES = ['cambiato_dopo_controllo', 'soppresso_dopo_controllo'] as const

const RECHECK_CODE_BY_LABEL: Record<string, (typeof RECHECK_CODES)[number]> = {
  'Cambiato dopo il controllo': 'cambiato_dopo_controllo',
  'Non esiste più nel testo vigente': 'soppresso_dopo_controllo',
}

/** The code of an outcome, with the re-check outcomes of older servers read from their label. */
export function statusCode(status: FindingStatus): string {
  if ((RECHECK_CODES as readonly string[]).includes(status.code)) return status.code
  return RECHECK_CODE_BY_LABEL[status.label] ?? status.code
}

/** The words of an outcome: ours for the codes the check produces today, the server's for any other. */
export function statusLabel(status: FindingStatus, t: Translate): string {
  const recheck = statusCode(status)
  if (recheck !== status.code || (RECHECK_CODES as readonly string[]).includes(recheck)) return t(`controlla.status.${recheck}`)
  const key = `controlla.status.${status.code}`
  if (status.code && /^[a-z_]+$/.test(status.code) && t.has(key)) return t(key)
  return status.label || status.code
}

/** "2 da correggere, 1 da controllare, 4 a posto": only the groups that have findings. */
export function countsLine(counts: CheckCounts, t: Translate): string {
  return GROUPS.filter((group) => counts[group] > 0)
    .map((group) => t(`controlla.list.counts.${group}`, { count: counts[group] }))
    .join(', ')
}

export function totalFindings(counts: CheckCounts): number {
  return GROUPS.reduce((sum, group) => sum + counts[group], 0)
}

/** "testo consolidato al 27 luglio 2026" or "testo originale", from the date of a version. */
export function versionLabel(asOf: string | null, ctx: TextContext): string {
  return asOf ? ctx.t('controlla.version.consolidated', { date: formatDate(asOf, ctx) }) : ctx.t('controlla.version.original')
}

/**
 * The server names a version in Italian with a numeric date ("testo
 * consolidato al 27/07/2026", "testo originale"). The two forms it uses are
 * rewritten in the words and the date format of the interface; anything else
 * is shown as it came.
 */
export function localizeVersionLabel(label: string | null | undefined, ctx: TextContext): string {
  const text = (label ?? '').trim()
  if (!text) return ctx.t('controlla.version.earlier')
  if (/^testo originale$/i.test(text)) return ctx.t('controlla.version.original')
  const m = /^testo consolidato al (\d{2})\/(\d{2})\/(\d{4})$/i.exec(text)
  if (m) return versionLabel(`${m[3]}-${m[2]}-${m[1]}`, ctx)
  return text
}

/** The act as the caption of a quoted passage names it: official name first, short name in brackets. */
export function actTitle(act: FindingAct | null, t: Translate): string {
  if (!act) return t('controlla.finding.noAct')
  if (act.source === 'eurlex' && isCelex(act.id)) return actOfCelex(act.id, t)
  return act.label || act.name || act.id
}

/** "EUR-Lex" or "Normattiva", from the link when it says so, else from the source of the act. */
export function originName(url: string | null | undefined, source?: string): string | undefined {
  const fromUrl = originOf(url ?? undefined)
  if (fromUrl) return fromUrl
  if (source === 'eurlex') return 'EUR-Lex'
  if (source === 'normattiva') return 'Normattiva'
  return undefined
}

/**
 * Where to read a provision the document depends on. The API gives no link
 * for a dependency: for an EU act it is the page of the act on EUR-Lex, which
 * lists its consolidated versions; for an Italian act the Normattiva address
 * built from its URN.
 */
export function dependencyUrl(dependency: Pick<Dependency, 'source' | 'act'>, locale: string): string | undefined {
  if (dependency.source === 'eurlex' && isCelex(dependency.act)) return eurlexUrl(dependency.act, eurlexLang(locale))
  if (dependency.source === 'normattiva' && /^urn:nir:[a-z0-9.:;~@-]+$/i.test(dependency.act)) {
    return `https://www.normattiva.it/uri-res/N2Ls?${dependency.act}`
  }
  return undefined
}

/** A link the page can offer: http(s) and pointing somewhere. */
export function safeUrl(url: string | null | undefined): string | undefined {
  return isUsefulUrl(url) ? url : undefined
}
