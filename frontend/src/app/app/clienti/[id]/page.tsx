'use client'

import { useCallback, useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { ArrowLeft, Pencil, Trash2 } from 'lucide-react'
import { Button, ButtonLink, EmptyState, PageHeader, Skeleton, Tabs } from '@/components/ui'
import { useErrorText } from '@/i18n/errors'
import type { Client } from '@/lib/types'
import { ClientFormDialog } from '@/components/clienti/ClientFormDialog'
import { ComplianceTab } from '@/components/clienti/ComplianceTab'
import { DeleteClientDialog } from '@/components/clienti/DeleteClientDialog'
import { DocumentsTab } from '@/components/clienti/DocumentsTab'
import { ProfileTab } from '@/components/clienti/ProfileTab'
import { fetchClient } from '@/components/clienti/clients-api'
import { formatIsoDate } from '@/components/clienti/format'

const TAB_IDS = ['profilo', 'conformita', 'documenti'] as const
type TabId = (typeof TAB_IDS)[number]

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'missing' }
  | { status: 'ready'; client: Client }

export default function ClienteDetailPage() {
  const t = useTranslations('clienti')
  const tu = useTranslations('ui')
  const errorText = useErrorText()
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
      setState({ status: 'error', message: errorText(err, 'errors.loadFailed') })
    }
  }, [errorText, id])

  useEffect(() => {
    load()
  }, [load])

  const back = (
    <ButtonLink href="/app/clienti" variant="ghost" size="sm" iconLeft={<ArrowLeft className="h-4 w-4" aria-hidden="true" />}>
      {t('detail.back')}
    </ButtonLink>
  )

  if (state.status === 'loading') {
    return (
      <div>
        <div className="mb-4">{back}</div>
        <div className="space-y-3" role="status" aria-label={t('loadingOne')}>
          <Skeleton className="h-9 w-72" label={t('loadingOne')} />
          <Skeleton className="h-5 w-48" label={t('loadingOne')} />
          <Skeleton className="mt-6 h-10 w-full max-w-md" label={t('loadingOne')} />
          <Skeleton className="h-64" label={t('loadingOne')} />
        </div>
      </div>
    )
  }

  if (state.status === 'error') {
    return (
      <div>
        <div className="mb-4">{back}</div>
        <div role="alert" className="rounded-lg border border-bad/30 bg-surface p-5">
          <h1 className="text-h3">{t('loadFailedOneTitle')}</h1>
          <p className="mt-1 text-body text-ink-2">{state.message}</p>
          <Button variant="secondary" className="mt-4" onClick={load}>
            {tu('retryLoad')}
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
          title={t('detail.missingTitle')}
          description={t('detail.missingDescription')}
          action={<ButtonLink href="/app/clienti">{t('detail.goToList')}</ButtonLink>}
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
    created ? t('detail.createdOn', { date: created }) : null,
    updated ? t('detail.updatedOn', { date: updated }) : null,
  ].filter(Boolean)
  const tabs = TAB_IDS.map((tabId) => ({ id: tabId, label: t(`detail.tabs.${tabId}`) }))

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
              {t('detail.edit')}
            </Button>
            <Button variant="danger" onClick={() => setDeleting(true)} iconLeft={<Trash2 className="h-4 w-4" aria-hidden="true" />}>
              {t('detail.delete')}
            </Button>
          </>
        }
      />

      <Tabs tabs={tabs} value={tab} onChange={(next) => setTab(next as TabId)} label={t('detail.tabsLabel')} className="mb-6" />

      <div role="tabpanel" aria-label={t(`detail.tabs.${tab}`)}>
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
