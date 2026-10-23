'use client'

import { Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { ListChecks } from 'lucide-react'
import { PageHeader } from '@/components/ui/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { Skeleton } from '@/components/ui/Skeleton'
import { useToast } from '@/components/ui/Toast'
import { EU_COUNTRY_CODES, ScopeForm } from '@/components/ambito/ScopeForm'
import { ScopeResults } from '@/components/ambito/ScopeResults'
import { copyText } from '@/components/ambito/clipboard'
import { loadClients, type ClientOption } from '@/components/ambito/clients'
import { formatDate } from '@/i18n/format'
import { useTextContext } from '@/i18n/useTextContext'
import { assessScope } from '@/lib/scope/rules'
import { EMPTY_INPUT, inputToQuery, queryToInput } from '@/lib/scope/query'
import { VERIFIED_ON } from '@/lib/scope/sources'
import { assessmentToText } from '@/lib/scope/text'
import type { ScopeAssessment, ScopeInput } from '@/lib/scope/types'

function canAssess(input: ScopeInput): boolean {
  return input.employees != null || input.turnoverEur != null || input.euTurnoverEur != null || input.ai != null
}

export default function AmbitoPage() {
  const t = useTranslations('ambito')
  return (
    <Suspense fallback={<Skeleton className="h-64" label={t('loading')} />}>
      <AmbitoView />
    </Suspense>
  )
}

function AmbitoView() {
  const t = useTranslations('ambito')
  const ctx = useTextContext()
  const params = useSearchParams()
  const router = useRouter()
  const pathname = usePathname()
  const { toast } = useToast()

  const [input, setInput] = useState<ScopeInput>(() => queryToInput(params.toString()) ?? EMPTY_INPUT)
  const [assessment, setAssessment] = useState<ScopeAssessment | null>(() => {
    const fromUrl = queryToInput(params.toString())
    return fromUrl ? assessScope(fromUrl, ctx) : null
  })
  const [formError, setFormError] = useState<string | undefined>()
  const [clients, setClients] = useState<ClientOption[]>([])
  const [clientsLoading, setClientsLoading] = useState(true)
  const lastQuery = useRef(params.toString())

  // Follow the URL when it changes from outside this page (back, forward, a shared link).
  useEffect(() => {
    const q = params.toString()
    if (q === lastQuery.current) return
    lastQuery.current = q
    const next = queryToInput(q)
    if (next) {
      setInput(next)
      setAssessment(assessScope(next, ctx))
    } else {
      setInput(EMPTY_INPUT)
      setAssessment(null)
    }
  }, [params, ctx])

  // A language change re-words the result that is on screen.
  useEffect(() => {
    setAssessment((current) => (current ? assessScope(current.input, ctx) : current))
  }, [ctx])

  useEffect(() => {
    let cancelled = false
    loadClients()
      .then((list) => {
        if (!cancelled) setClients(list)
      })
      .catch(() => {
        if (!cancelled) setClients([])
      })
      .finally(() => {
        if (!cancelled) setClientsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const verify = useCallback(() => {
    if (!canAssess(input)) {
      setFormError(t('formError'))
      return
    }
    setFormError(undefined)
    setAssessment(assessScope(input, ctx))
    const q = inputToQuery(input).toString()
    lastQuery.current = q
    router.replace(`${pathname}?${q}`, { scroll: false })
  }, [ctx, input, pathname, router, t])

  const reset = useCallback(() => {
    setAssessment(null)
    setFormError(undefined)
    lastQuery.current = ''
    router.replace(pathname, { scroll: false })
  }, [pathname, router])

  const loadClient = (id: string) => {
    const c = clients.find((x) => x.id === id)
    if (!c) return
    const country = c.jurisdictions?.find((j) => (EU_COUNTRY_CODES as readonly string[]).includes(j))
    setInput((prev) => ({
      ...prev,
      name: c.name,
      employees: c.employee_count ?? prev.employees,
      turnoverEur: c.revenue_eur ?? prev.turnoverEur,
      sector: c.sector ?? prev.sector,
      country: country ?? prev.country,
    }))
  }

  const copyResult = async () => {
    if (!assessment) return
    const ok = await copyText(assessmentToText(assessment, ctx))
    toast(
      ok
        ? { kind: 'ok', title: t('copy.ok') }
        : { kind: 'bad', title: t('copy.failed'), description: t('copy.resultFailed') },
    )
  }

  const copyLink = async () => {
    const ok = await copyText(window.location.href)
    toast(
      ok
        ? { kind: 'ok', title: t('copy.ok') }
        : { kind: 'bad', title: t('copy.failed'), description: t('copy.linkFailed') },
    )
  }

  return (
    <div>
      <PageHeader
        title={t('title')}
        description={t('description')}
        meta={t('meta', { date: formatDate(VERIFIED_ON, ctx) })}
      />
      <div className="grid gap-8 lg:grid-cols-12">
        <div className="lg:col-span-5">
          <ScopeForm
            value={input}
            onChange={setInput}
            onSubmit={verify}
            onReset={reset}
            clients={clients}
            clientsLoading={clientsLoading}
            onLoadClient={loadClient}
            error={formError}
          />
        </div>
        <div className="lg:col-span-7">
          {assessment ? (
            <ScopeResults assessment={assessment} onCopyResult={copyResult} onCopyLink={copyLink} />
          ) : (
            <EmptyState
              icon={<ListChecks className="h-8 w-8" aria-hidden="true" />}
              title={t('empty.title')}
              description={t('empty.description')}
            />
          )}
        </div>
      </div>
    </div>
  )
}
