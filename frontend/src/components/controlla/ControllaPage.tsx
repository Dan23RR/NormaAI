'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { FileCheck2 } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { PageHeader } from '@/components/ui/PageHeader'
import { Skeleton } from '@/components/ui/Skeleton'
import { Tabs } from '@/components/ui/Tabs'
import { fetchClients } from '@/components/clienti/clients-api'
import { useAuth } from '@/hooks/useAuth'
import type { Client } from '@/lib/types'
import { CheckForm } from './CheckForm'
import { ChecksTable } from './ChecksTable'
import { PAGE_SIZE, fetchChecks, rememberCheck } from './documents-api'
import { EmailDigestToggle } from './EmailDigestToggle'
import { describeFailure, type Failure } from './errors'
import { FailureMessage } from './FailureMessage'
import { StorageNote } from './StorageNote'
import type { CheckSummary, DocumentCheck } from './types'

type Filter = 'all' | 'review'

type ListState =
  | { status: 'loading' }
  | { status: 'error'; failure: Failure }
  | { status: 'ready'; items: CheckSummary[]; total: number }

type ClientsState = { status: 'loading' } | { status: 'failed' } | { status: 'ready'; clients: Client[] }

/**
 * The surface where a document is checked: the form with the note on what
 * is kept, then the documents checked so far, all of them or only those a
 * re-check marked for review.
 */
export function ControllaPage() {
  const t = useTranslations('controlla')
  const tu = useTranslations('ui')
  const router = useRouter()
  const searchParams = useSearchParams()
  const { demoMode } = useAuth()
  // The page of a client links here with ?cliente=<id>: that client is preselected.
  const preselected = searchParams.get('cliente') ?? undefined

  const [clientsState, setClientsState] = useState<ClientsState>({ status: 'loading' })
  const [filter, setFilter] = useState<Filter>('all')
  const [list, setList] = useState<ListState>({ status: 'loading' })
  const [totals, setTotals] = useState<{ all: number | null; review: number | null }>({ all: null, review: null })
  const [loadingMore, setLoadingMore] = useState(false)
  const [moreFailure, setMoreFailure] = useState<Failure | null>(null)
  // Only the answer to the latest request may touch the list.
  const request = useRef(0)

  useEffect(() => {
    let alive = true
    fetchClients()
      .then((clients) => {
        if (alive) setClientsState({ status: 'ready', clients })
      })
      .catch(() => {
        if (alive) setClientsState({ status: 'failed' })
      })
    return () => {
      alive = false
    }
  }, [])

  const load = useCallback(async (which: Filter) => {
    const mine = ++request.current
    setList({ status: 'loading' })
    setMoreFailure(null)
    try {
      const res = await fetchChecks({ needsReview: which === 'review', limit: PAGE_SIZE, offset: 0 })
      if (request.current !== mine) return
      setList({ status: 'ready', items: res.items, total: res.total })
      setTotals((prev) => ({ ...prev, [which]: res.total }))
    } catch (err) {
      if (request.current !== mine) return
      setList({ status: 'error', failure: describeFailure(err) })
    }
  }, [])

  useEffect(() => {
    void load(filter)
  }, [load, filter])

  // How many are to review, for the tab, without waiting for a click on it.
  useEffect(() => {
    let alive = true
    fetchChecks({ needsReview: true, limit: 1, offset: 0 })
      .then((res) => {
        if (alive) setTotals((prev) => ({ ...prev, review: prev.review ?? res.total }))
      })
      .catch(() => {
        /* the tab simply shows no count */
      })
    return () => {
      alive = false
    }
  }, [])

  const loadMore = async () => {
    if (list.status !== 'ready' || loadingMore) return
    const mine = request.current
    setLoadingMore(true)
    setMoreFailure(null)
    try {
      const res = await fetchChecks({ needsReview: filter === 'review', limit: PAGE_SIZE, offset: list.items.length })
      if (request.current !== mine) return
      setList((prev) => {
        if (prev.status !== 'ready') return prev
        const known = new Set(prev.items.map((item) => item.id))
        return { status: 'ready', items: [...prev.items, ...res.items.filter((item) => !known.has(item.id))], total: res.total }
      })
    } catch (err) {
      if (request.current === mine) setMoreFailure(describeFailure(err))
    } finally {
      setLoadingMore(false)
    }
  }

  const onChecked = (check: DocumentCheck) => {
    rememberCheck(check, demoMode)
    router.push(`/app/controlla/${encodeURIComponent(check.id)}`)
  }

  const clients = clientsState.status === 'ready' ? clientsState.clients : []
  const clientNames = useMemo(
    () => (clientsState.status === 'ready' ? new Map(clientsState.clients.map((c) => [c.id, c.name])) : null),
    [clientsState],
  )
  const tabs = [
    { id: 'all', label: t('list.all'), count: totals.all ?? undefined },
    { id: 'review', label: t('list.review'), count: totals.review ?? undefined },
  ]

  return (
    <div>
      <PageHeader title={t('title')} description={t('description')} />

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_320px]">
        <CheckForm
          clients={clients}
          clientsFailed={clientsState.status === 'failed'}
          initialClientId={preselected}
          demo={demoMode}
          onChecked={onChecked}
        />
        <StorageNote />
      </div>

      <section aria-labelledby="checks-heading" className="mt-10 border-t border-rule pt-8">
        <div className="flex flex-wrap items-start justify-between gap-x-8 gap-y-4">
          <h2 id="checks-heading" className="text-h3">
            {t('list.heading')}
          </h2>
          <EmailDigestToggle demo={demoMode} className="max-w-sm" />
        </div>

        <Tabs
          tabs={tabs}
          value={filter}
          onChange={(id) => setFilter(id === 'review' ? 'review' : 'all')}
          label={t('list.filterLabel')}
          className="mt-4"
        />

        <div className="mt-4" role="tabpanel" aria-label={filter === 'review' ? t('list.review') : t('list.all')}>
          {list.status === 'loading' && (
            <div className="space-y-2" role="status" aria-label={t('list.loading')}>
              <Skeleton className="h-10" label={t('list.loading')} />
              <Skeleton className="h-14" label={t('list.loading')} />
              <Skeleton className="h-14" label={t('list.loading')} />
            </div>
          )}

          {list.status === 'error' && (
            <FailureMessage
              failure={list.failure}
              title={t('list.loadFailedTitle')}
              action={
                <Button variant="secondary" onClick={() => void load(filter)}>
                  {tu('retryLoad')}
                </Button>
              }
            />
          )}

          {list.status === 'ready' && list.items.length === 0 && filter === 'all' && (
            <EmptyState
              icon={<FileCheck2 className="h-8 w-8" aria-hidden="true" />}
              title={t('list.emptyTitle')}
              description={t('list.emptyDescription')}
            />
          )}

          {list.status === 'ready' && list.items.length === 0 && filter === 'review' && (
            <EmptyState
              title={t('list.emptyReviewTitle')}
              description={t('list.emptyReviewDescription')}
              action={
                <Button variant="secondary" onClick={() => setFilter('all')}>
                  {t('list.showAll')}
                </Button>
              }
            />
          )}

          {list.status === 'ready' && list.items.length > 0 && (
            <>
              <ChecksTable items={list.items} clients={clientNames} />
              <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                <p className="text-small text-ink-2" aria-live="polite">
                  {t('list.shown', { shown: list.items.length, total: list.total })}
                </p>
                {list.items.length < list.total && (
                  <Button variant="secondary" size="sm" onClick={loadMore} loading={loadingMore}>
                    {t('list.more')}
                  </Button>
                )}
              </div>
              {moreFailure && <FailureMessage failure={moreFailure} className="mt-3" />}
            </>
          )}
        </div>
      </section>
    </div>
  )
}
