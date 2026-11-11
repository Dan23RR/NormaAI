'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { AlertTriangle } from 'lucide-react'
import { Badge } from '@/components/ui/Badge'
import { TBody, TD, TH, THead, TR, Table } from '@/components/ui/Table'
import { formatIsoDate } from '@/components/clienti/format'
import { countsLine, totalFindings } from './labels'
import { GroupBadge } from './Outcome'
import type { CheckSummary } from './types'

/** The names of the clients by id; null while they are not known (loading, or the list failed). */
export type ClientNames = Map<string, string> | null

/**
 * The state of a check in one glance. A check to review says so first: the
 * outcome of the day it was made no longer tells the whole story.
 */
function StatusCell({ item }: { item: CheckSummary }) {
  const t = useTranslations('controlla.list')
  const tRoot = useTranslations()
  if (item.needs_review) {
    return (
      <div>
        <Badge tone="warn">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          {t('needsReview')}
        </Badge>
        <p className="mt-1 text-caption text-ink-2">{t('needsReviewHint')}</p>
      </div>
    )
  }
  if (totalFindings(item.counts) === 0) return <span className="text-small text-ink-2">{t('noReferences')}</span>
  return (
    <div>
      <GroupBadge group={item.status} />
      <p className="mt-1 text-caption text-ink-2">{countsLine(item.counts, tRoot)}</p>
    </div>
  )
}

function ClientCell({ item, clients }: { item: CheckSummary; clients: ClientNames }) {
  const t = useTranslations('controlla.list')
  const tu = useTranslations('ui')
  if (!item.client_id) return <span className="text-ink-3">{t('noClient')}</span>
  if (!clients) return <span className="text-ink-3">{tu('notAvailable')}</span>
  const name = clients.get(item.client_id)
  if (!name) return <span className="text-ink-3">{t('clientGone')}</span>
  return (
    <Link
      href={`/app/clienti/${encodeURIComponent(item.client_id)}`}
      className="text-ink no-underline hover:underline"
      onClick={(event) => event.stopPropagation()}
    >
      {name}
    </Link>
  )
}

/** The checked documents: a row per check, the name leads to its page. */
export function ChecksTable({
  items,
  clients = null,
  showClient = true,
}: {
  items: CheckSummary[]
  clients?: ClientNames
  /** False on the page of a client, where every row is of that client. */
  showClient?: boolean
}) {
  const t = useTranslations('controlla.list')
  const tu = useTranslations('ui')
  const router = useRouter()

  return (
    <Table>
      <THead>
        <TR>
          <TH>{t('colDocument')}</TH>
          <TH>{t('colStatus')}</TH>
          {showClient && <TH className="hidden md:table-cell">{t('colClient')}</TH>}
          <TH className="hidden sm:table-cell">{t('colChecked')}</TH>
          <TH className="hidden lg:table-cell">{t('colWatch')}</TH>
        </TR>
      </THead>
      <TBody>
        {items.map((item) => {
          const href = `/app/controlla/${encodeURIComponent(item.id)}`
          const checked = formatIsoDate(item.checked_at)
          return (
            <TR key={item.id} className="cursor-pointer transition-colors hover:bg-surface-3" onClick={() => router.push(href)}>
              <TD>
                <Link
                  href={href}
                  className="break-words font-medium text-ink no-underline hover:underline"
                  onClick={(event) => event.stopPropagation()}
                >
                  {item.filename}
                </Link>
                {/* On a narrow screen the date moves under the name. */}
                {checked && <p className="mt-0.5 text-caption tabular text-ink-2 sm:hidden">{checked}</p>}
              </TD>
              <TD>
                <StatusCell item={item} />
              </TD>
              {showClient && (
                <TD className="hidden md:table-cell">
                  <ClientCell item={item} clients={clients} />
                </TD>
              )}
              <TD className="hidden tabular text-ink-2 sm:table-cell">{checked ?? <span className="text-ink-3">{tu('notAvailable')}</span>}</TD>
              <TD className="hidden text-ink-2 lg:table-cell">{item.watch ? t('watchOn') : t('watchOff')}</TD>
            </TR>
          )
        })}
      </TBody>
    </Table>
  )
}
