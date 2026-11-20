'use client'

import { useCallback, useEffect, useState } from 'react'
import { useTranslations } from 'next-intl'
import { FileCheck2 } from 'lucide-react'
import { Button, ButtonLink, EmptyState, Skeleton } from '@/components/ui'
import { ChecksTable } from '@/components/controlla/ChecksTable'
import { fetchChecks } from '@/components/controlla/documents-api'
import { describeFailure, type Failure } from '@/components/controlla/errors'
import { FailureMessage } from '@/components/controlla/FailureMessage'
import type { CheckSummary } from '@/components/controlla/types'
import type { Client } from '@/lib/types'

/** How many checks of a client the tab asks for; the rest is in Controlla. */
const LIMIT = 50

type State =
  | { status: 'loading' }
  | { status: 'error'; failure: Failure }
  | { status: 'ready'; items: CheckSummary[]; total: number }

/**
 * The documents checked for this client (GET /api/v1/documents/checks?client_id=),
 * and the way to check another one with the client already chosen.
 *
 * This tab used to upload a file to POST /api/v1/documents/upload, which
 * indexes the text for the whole organisation, keeps no list and offers no
 * deletion: nothing a person could see or undo from here, and nothing that
 * belonged to the client. It was folded into the check, where the file is
 * not stored and every check can be opened, re-checked and deleted.
 */
export function DocumentsTab({ client }: { client: Client }) {
  const t = useTranslations('clienti.documents')
  const tu = useTranslations('ui')
  const [state, setState] = useState<State>({ status: 'loading' })

  const load = useCallback(async () => {
    setState({ status: 'loading' })
    try {
      const res = await fetchChecks({ clientId: client.id, limit: LIMIT, offset: 0 })
      setState({ status: 'ready', items: res.items, total: res.total })
    } catch (err) {
      setState({ status: 'error', failure: describeFailure(err) })
    }
  }, [client.id])

  useEffect(() => {
    void load()
  }, [load])

  const checkLink = (
    <ButtonLink
      href={`/app/controlla?cliente=${encodeURIComponent(client.id)}`}
      iconLeft={<FileCheck2 className="h-4 w-4" aria-hidden="true" />}
    >
      {t('check')}
    </ButtonLink>
  )
  const hasItems = state.status === 'ready' && state.items.length > 0

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div className="min-w-0 max-w-prose">
          <h3 className="text-h4">{t('title')}</h3>
          <p className="mt-1 text-small text-ink-2">{t('lead', { name: client.name })}</p>
        </div>
        {/* With an empty list the same link is the action of the empty state. */}
        {(hasItems || state.status === 'error') && checkLink}
      </div>

      {state.status === 'loading' && (
        <div className="space-y-2" role="status" aria-label={t('loading')}>
          <Skeleton className="h-10" label={t('loading')} />
          <Skeleton className="h-14" label={t('loading')} />
        </div>
      )}

      {state.status === 'error' && (
        <FailureMessage
          failure={state.failure}
          title={t('loadFailedTitle')}
          action={
            <Button variant="secondary" onClick={load}>
              {tu('retryLoad')}
            </Button>
          }
        />
      )}

      {state.status === 'ready' && state.items.length === 0 && (
        <EmptyState
          icon={<FileCheck2 className="h-8 w-8" aria-hidden="true" />}
          title={t('emptyTitle')}
          description={t('emptyDescription', { name: client.name })}
          action={checkLink}
        />
      )}

      {state.status === 'ready' && state.items.length > 0 && (
        <>
          <ChecksTable items={state.items} showClient={false} />
          {state.total > state.items.length && (
            <p className="text-small text-ink-2">{t('partial', { shown: state.items.length, total: state.total })}</p>
          )}
        </>
      )}
    </div>
  )
}
