'use client'

import { useCallback, useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { ArrowLeft, Pencil, Trash2 } from 'lucide-react'
import { Button, ButtonLink, EmptyState, PageHeader, Skeleton, Tabs } from '@/components/ui'
import type { Client } from '@/lib/types'
import { ClientFormDialog } from '@/components/clienti/ClientFormDialog'
import { ComplianceTab } from '@/components/clienti/ComplianceTab'
import { DeleteClientDialog } from '@/components/clienti/DeleteClientDialog'
import { DocumentsTab } from '@/components/clienti/DocumentsTab'
import { ProfileTab } from '@/components/clienti/ProfileTab'
import { fetchClient } from '@/components/clienti/clients-api'
import { formatIsoDate } from '@/components/clienti/format'

type TabId = 'profilo' | 'conformita' | 'documenti'

const TABS: Array<{ id: TabId; label: string }> = [
  { id: 'profilo', label: 'Profilo' },
  { id: 'conformita', label: 'Analisi di conformità' },
  { id: 'documenti', label: 'Documenti' },
]

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'missing' }
  | { status: 'ready'; client: Client }

export default function ClienteDetailPage() {
  const params = useParams<{ id: string }>()
  const router = useRouter()
  const id = typeof params?.id === 'string' ? params.id : ''
  const [state, setState] = useState<LoadState>({ status: 'loading' })
  const [tab, setTab] = useState<TabId>('profilo')
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const load = useCallback(async () => {
    if (!id) return
    setState({ status: 'loading' })
    try {
      const client = await fetchClient(id)
      setState(client ? { status: 'ready', client } : { status: 'missing' })
    } catch (err) {
      setState({ status: 'error', message: err instanceof Error ? err.message : 'Caricamento non riuscito.' })
    }
  }, [id])

  useEffect(() => {
    load()
  }, [load])

  const back = (
    <ButtonLink href="/app/clienti" variant="ghost" size="sm" iconLeft={<ArrowLeft className="h-4 w-4" aria-hidden="true" />}>
      Tutti i clienti
    </ButtonLink>
  )

  if (state.status === 'loading') {
    return (
      <div>
        <div className="mb-4">{back}</div>
        <div className="space-y-3" role="status" aria-label="Caricamento del cliente">
          <Skeleton className="h-9 w-72" label="Caricamento del cliente" />
          <Skeleton className="h-5 w-48" label="Caricamento del cliente" />
          <Skeleton className="mt-6 h-10 w-full max-w-md" label="Caricamento del cliente" />
          <Skeleton className="h-64" label="Caricamento del cliente" />
        </div>
      </div>
    )
  }

  if (state.status === 'error') {
    return (
      <div>
        <div className="mb-4">{back}</div>
        <div role="alert" className="rounded-lg border border-bad/30 bg-surface p-5">
          <h1 className="text-h3">Il cliente non si è caricato</h1>
          <p className="mt-1 text-body text-ink-2">{state.message}</p>
          <Button variant="secondary" className="mt-4" onClick={load}>
            Riprova il caricamento
          </Button>
        </div>
      </div>
    )
  }

  if (state.status === 'missing') {
    return (
      <div>
        <div className="mb-4">{back}</div>
        <EmptyState
          title="Cliente non trovato"
          description="Il cliente non esiste o è stato eliminato. Torna all’elenco per sceglierne un altro."
          action={<ButtonLink href="/app/clienti">Vai all’elenco dei clienti</ButtonLink>}
        />
      </div>
    )
  }

  const { client } = state
  const created = formatIsoDate(client.created_at)
  const updated = formatIsoDate(client.updated_at)
  const countries = (client.jurisdictions ?? []).join(', ')
  const subtitle = client.sector
    ? countries
      ? `${client.sector} (${countries})`
      : client.sector
    : countries || undefined
  const metaParts = [
    created ? `Creato il ${created}` : null,
    updated ? `aggiornato il ${updated}` : null,
  ].filter(Boolean)

  return (
    <div>
      <div className="mb-4">{back}</div>
      <PageHeader
        title={client.name}
        description={subtitle}
        meta={metaParts.length > 0 ? <span className="tabular">{metaParts.join(', ')}</span> : undefined}
        actions={
          <>
            <Button variant="secondary" onClick={() => setEditing(true)} iconLeft={<Pencil className="h-4 w-4" aria-hidden="true" />}>
              Modifica
            </Button>
            <Button variant="danger" onClick={() => setDeleting(true)} iconLeft={<Trash2 className="h-4 w-4" aria-hidden="true" />}>
              Elimina
            </Button>
          </>
        }
      />

      <Tabs tabs={TABS} value={tab} onChange={(next) => setTab(next as TabId)} label="Sezioni del cliente" className="mb-6" />

      <div role="tabpanel" aria-label={TABS.find((t) => t.id === tab)?.label}>
        {tab === 'profilo' && <ProfileTab client={client} onEdit={() => setEditing(true)} />}
        {tab === 'conformita' && <ComplianceTab client={client} />}
        {tab === 'documenti' && <DocumentsTab client={client} />}
      </div>

      <ClientFormDialog
        open={editing}
        onClose={() => setEditing(false)}
        client={client}
        onSaved={(saved) => setState({ status: 'ready', client: saved })}
      />
      <DeleteClientDialog
        open={deleting}
        onClose={() => setDeleting(false)}
        client={client}
        onDeleted={() => router.push('/app/clienti')}
      />
    </div>
  )
}
