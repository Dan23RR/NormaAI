'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Building2, Plus, Search } from 'lucide-react'
import { Button, EmptyState, Input, PageHeader, Skeleton } from '@/components/ui'
import type { Client } from '@/lib/types'
import { ClientFormDialog } from '@/components/clienti/ClientFormDialog'
import { ClientsTable } from '@/components/clienti/ClientsTable'
import { fetchClients } from '@/components/clienti/clients-api'

type LoadState = { status: 'loading' } | { status: 'error'; message: string } | { status: 'ready' }

export default function ClientiPage() {
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
      setState({ status: 'error', message: err instanceof Error ? err.message : 'Caricamento non riuscito.' })
    }
  }, [])

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
      Nuovo cliente
    </Button>
  )

  return (
    <div>
      <PageHeader
        title="Clienti"
        description="Le aziende che segui: il profilo, le analisi di conformità e i documenti di ciascuna."
        actions={newClientButton}
      />

      {state.status === 'ready' && clients.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="relative w-full max-w-sm">
            <label htmlFor="clients-search" className="sr-only">
              Cerca tra i clienti
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
              placeholder="Cerca per nome o settore"
              className="pl-9"
            />
          </div>
          <p className="text-small text-ink-2" aria-live="polite">
            {filtered.length === clients.length
              ? `${clients.length} ${clients.length === 1 ? 'cliente' : 'clienti'}`
              : `${filtered.length} di ${clients.length} clienti`}
          </p>
        </div>
      )}

      {state.status === 'loading' && (
        <div className="space-y-2" role="status" aria-label="Caricamento dei clienti">
          <Skeleton className="h-10" label="Caricamento dei clienti" />
          <Skeleton className="h-12" label="Caricamento dei clienti" />
          <Skeleton className="h-12" label="Caricamento dei clienti" />
          <Skeleton className="h-12" label="Caricamento dei clienti" />
        </div>
      )}

      {state.status === 'error' && (
        <div role="alert" className="rounded-lg border border-bad/30 bg-surface p-5">
          <h2 className="text-h4">I clienti non si sono caricati</h2>
          <p className="mt-1 text-body text-ink-2">{state.message}</p>
          <Button variant="secondary" className="mt-4" onClick={load}>
            Riprova il caricamento
          </Button>
        </div>
      )}

      {state.status === 'ready' && clients.length === 0 && (
        <EmptyState
          icon={<Building2 className="h-8 w-8" aria-hidden="true" />}
          title="Nessun cliente ancora"
          description="Crea il profilo della prima azienda che segui: nome, settore, dimensione e framework. Da lì partono analisi e report."
          action={newClientButton}
        />
      )}

      {state.status === 'ready' && clients.length > 0 && filtered.length === 0 && (
        <EmptyState
          title={`Nessun cliente corrisponde a «${search.trim()}»`}
          description="Prova con un altro nome o un altro settore."
          action={
            <Button variant="secondary" onClick={() => setSearch('')}>
              Cancella la ricerca
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
