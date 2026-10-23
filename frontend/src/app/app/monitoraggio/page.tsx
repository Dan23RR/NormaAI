'use client'

import { Suspense, useCallback, useEffect, useState } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { PageHeader } from '@/components/ui/PageHeader'
import { Skeleton } from '@/components/ui/Skeleton'
import { Tabs } from '@/components/ui/Tabs'
import { AlertsTab, normaliseSummary } from '@/components/monitoraggio/AlertsTab'
import { AnalyzeTab } from '@/components/monitoraggio/AnalyzeTab'
import { DeadlinesTab } from '@/components/monitoraggio/DeadlinesTab'
import { useDateFormat } from '@/i18n/useDateFormat'
import { api } from '@/lib/api'
import { VERIFIED_ON } from '@/lib/scope/sources'

const TAB_IDS = ['scadenze', 'avvisi', 'analizza'] as const
type TabId = (typeof TAB_IDS)[number]

function isTabId(value: string | null): value is TabId {
  return value != null && (TAB_IDS as readonly string[]).includes(value)
}

export default function MonitoraggioPage() {
  const t = useTranslations('monitoraggio')
  return (
    <Suspense fallback={<Skeleton className="h-64" label={t('loading')} />}>
      <MonitoraggioView />
    </Suspense>
  )
}

function MonitoraggioView() {
  const t = useTranslations('monitoraggio')
  const formatDate = useDateFormat()
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
        title={t('title')}
        description={t('description')}
        meta={t('meta', { date: formatDate(VERIFIED_ON) })}
      />
      <Tabs
        label={t('tabsLabel')}
        className="mb-6"
        value={tab}
        onChange={change}
        tabs={[
          { id: 'scadenze', label: t('tabs.scadenze') },
          { id: 'avvisi', label: t('tabs.avvisi'), count: unread },
          { id: 'analizza', label: t('tabs.analizza') },
        ]}
      />
      <div role="tabpanel" aria-label={t(`tabs.${tab}`)}>
        {tab === 'scadenze' && <DeadlinesTab />}
        {tab === 'avvisi' && <AlertsTab onUnreadChange={setUnread} />}
        {tab === 'analizza' && <AnalyzeTab />}
      </div>
    </div>
  )
}
