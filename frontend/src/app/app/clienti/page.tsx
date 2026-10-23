'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslations } from 'next-intl'
import { Building2, Plus, Search } from 'lucide-react'
import { Button, EmptyState, Input, PageHeader, Skeleton } from '@/components/ui'
import { useErrorText } from '@/i18n/errors'
import type { Client } from '@/lib/types'
import { ClientFormDialog } from '@/components/clienti/ClientFormDialog'
import { ClientsTable } from '@/components/clienti/ClientsTable'
import { fetchClients } from '@/components/clienti/clients-api'

type LoadState = { status: 'loading' } | { status: 'error'; message: string } | { status: 'ready' }

export default function ClientiPage() {
  const t = useTranslations('clienti')
  const tu = useTranslations('ui')
  const errorText = useErrorText()
  const [clients, setClients] = useState<Client[]>([])
  const [state, setState] = useState<LoadState>({ status: 'loading' })
  const [search, setSearch] = useState('')
  const [creating, setCreating] = useState(false)

  const load = useCallback(async () => {
    setState({ status: 'loading' })
    try {
      setClients(await fetchClients())
      setState({ status: 'ready' })
    } catch (err) {
      setState({ status: 'error', message: errorText(err, 'errors.loadFailed') })
    }
  }, [errorText])

  useEffect(() => {
    load()
  }, [load])

  const query = search.trim().toLowerCase()
  const filtered = useMemo(
    () =>
      query
        ? clients.filter(
            (c) => c.name.toLowerCase().includes(query) || (c.sector ?? '').toLowerCase().includes(query),
          )
        : clients,
    [clients, query],
  )

  const newClientButton = (
    <Button onClick={() => setCreating(true)} iconLeft={<Plus className="h-4 w-4" aria-hidden="true" />}>
      {t('newClient')}
    </Button>
  )

  return (
    <div>
      <PageHeader title={t('title')} description={t('description')} actions={newClientButton} />

      {state.status === 'ready' && clients.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="relative w-full max-w-sm">
            <label htmlFor="clients-search" className="sr-only">
              {t('search')}
            </label>
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3"
              aria-hidden="true"
            />
            <Input
              id="clients-search"
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t('searchPlaceholder')}
              className="pl-9"
            />
          </div>
          <p className="text-small text-ink-2" aria-live="polite">
            {filtered.length === clients.length
              ? t('count', { count: clients.length })
              : t('countFiltered', { shown: filtered.length, total: clients.length })}
          </p>
        </div>
      )}

      {state.status === 'loading' && (
        <div className="space-y-2" role="status" aria-label={t('loading')}>
          <Skeleton className="h-10" label={t('loading')} />
          <Skeleton className="h-12" label={t('loading')} />
          <Skeleton className="h-12" label={t('loading')} />
          <Skeleton className="h-12" label={t('loading')} />
        </div>
      )}

      {state.status === 'error' && (
        <div role="alert" className="rounded-lg border border-bad/30 bg-surface p-5">
          <h2 className="text-h4">{t('loadFailedTitle')}</h2>
          <p className="mt-1 text-body text-ink-2">{state.message}</p>
          <Button variant="secondary" className="mt-4" onClick={load}>
            {tu('retryLoad')}
          </Button>
        </div>
      )}

      {state.status === 'ready' && clients.length === 0 && (
        <EmptyState
          icon={<Building2 className="h-8 w-8" aria-hidden="true" />}
          title={t('emptyTitle')}
          description={t('emptyDescription')}
          action={newClientButton}
        />
      )}

      {state.status === 'ready' && clients.length > 0 && filtered.length === 0 && (
        <EmptyState
          title={t('noMatchTitle', { query: search.trim() })}
          description={t('noMatchDescription')}
          action={
            <Button variant="secondary" onClick={() => setSearch('')}>
              {t('clearSearch')}
            </Button>
          }
        />
      )}

      {state.status === 'ready' && filtered.length > 0 && <ClientsTable clients={filtered} />}

      <ClientFormDialog
        open={creating}
        onClose={() => setCreating(false)}
        onSaved={(saved) => setClients((prev) => [saved, ...prev])}
      />
    </div>
  )
}
