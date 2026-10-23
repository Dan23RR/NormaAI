'use client'

import { Suspense, useCallback, useEffect, useState } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { PageHeader } from '@/components/ui/PageHeader'
import { Skeleton } from '@/components/ui/Skeleton'
import { Tabs } from '@/components/ui/Tabs'
import { AlertsTab, normaliseSummary } from '@/components/monitoraggio/AlertsTab'
import { AnalyzeTab } from '@/components/monitoraggio/AnalyzeTab'
import { DeadlinesTab } from '@/components/monitoraggio/DeadlinesTab'
import { api } from '@/lib/api'
import { formatDateIt } from '@/lib/obligations/dates'
import { VERIFIED_ON } from '@/lib/scope/sources'

const TAB_IDS = ['scadenze', 'avvisi', 'analizza'] as const
type TabId = (typeof TAB_IDS)[number]

function isTabId(value: string | null): value is TabId {
  return value != null && (TAB_IDS as readonly string[]).includes(value)
}

export default function MonitoraggioPage() {
  return (
    <Suspense fallback={<Skeleton className="h-64" label="Caricamento della pagina Monitoraggio" />}>
      <MonitoraggioView />
    </Suspense>
  )
}

function MonitoraggioView() {
  const params = useSearchParams()
  const router = useRouter()
  const pathname = usePathname()
  const fromUrl = params.get('tab')
  const [tab, setTab] = useState<TabId>(isTabId(fromUrl) ? fromUrl : 'scadenze')
  const [unread, setUnread] = useState<number | undefined>()

  useEffect(() => {
    if (isTabId(fromUrl) && fromUrl !== tab) setTab(fromUrl)
    if (fromUrl == null && tab !== 'scadenze') setTab('scadenze')
    // Only the URL drives this effect; `tab` is read, not depended on, to avoid a loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fromUrl])

  // The unread count on the tab comes from the summary endpoint, once; the Avvisi tab refreshes it.
  useEffect(() => {
    let cancelled = false
    api
      .get<unknown>('/api/v1/alerts/summary')
      .then((raw) => {
        const s = normaliseSummary(raw)
        if (!cancelled && s) setUnread(s.unread)
      })
      .catch(() => {
        /* the count stays hidden until the tab loads */
      })
    return () => {
      cancelled = true
    }
  }, [])

  const change = useCallback(
    (id: string) => {
      if (!isTabId(id)) return
      setTab(id)
      router.replace(id === 'scadenze' ? pathname : `${pathname}?tab=${id}`, { scroll: false })
    },
    [pathname, router],
  )

  return (
    <div>
      <PageHeader
        title="Monitoraggio"
        description="Le scadenze dei prossimi dodici mesi, gli avvisi per i vostri clienti e l’analisi di una novità normativa."
        meta={
          <>
            Calendario curato a mano; ogni voce indica la data di verifica (ultima verifica: {formatDateIt(VERIFIED_ON)}).
            Il controllo automatico delle novità su EUR-Lex non è ancora attivo.
          </>
        }
      />
      <Tabs
        label="Sezioni del monitoraggio"
        className="mb-6"
        value={tab}
        onChange={change}
        tabs={[
          { id: 'scadenze', label: 'Scadenze' },
          { id: 'avvisi', label: 'Avvisi', count: unread },
          { id: 'analizza', label: 'Analizza una novità' },
        ]}
      />
      <div role="tabpanel" aria-label={tab === 'scadenze' ? 'Scadenze' : tab === 'avvisi' ? 'Avvisi' : 'Analizza una novità'}>
        {tab === 'scadenze' && <DeadlinesTab />}
        {tab === 'avvisi' && <AlertsTab onUnreadChange={setUnread} />}
        {tab === 'analizza' && <AnalyzeTab />}
      </div>
    </div>
  )
}
