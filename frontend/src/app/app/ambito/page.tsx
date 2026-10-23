'use client'

import { Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { ListChecks } from 'lucide-react'
import { PageHeader } from '@/components/ui/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { Skeleton } from '@/components/ui/Skeleton'
import { useToast } from '@/components/ui/Toast'
import { EU_COUNTRIES, ScopeForm } from '@/components/ambito/ScopeForm'
import { ScopeResults } from '@/components/ambito/ScopeResults'
import { copyText } from '@/components/ambito/clipboard'
import { loadClients, type ClientOption } from '@/components/ambito/clients'
import { formatDateIt } from '@/lib/obligations/dates'
import { assessScope } from '@/lib/scope/rules'
import { EMPTY_INPUT, inputToQuery, queryToInput } from '@/lib/scope/query'
import { VERIFIED_ON } from '@/lib/scope/sources'
import { assessmentToText } from '@/lib/scope/text'
import type { ScopeAssessment, ScopeInput } from '@/lib/scope/types'

function canAssess(input: ScopeInput): boolean {
  return input.employees != null || input.turnoverEur != null || input.euTurnoverEur != null || input.ai != null
}

export default function AmbitoPage() {
  return (
    <Suspense fallback={<Skeleton className="h-64" label="Caricamento della pagina Ambito" />}>
      <AmbitoView />
    </Suspense>
  )
}

function AmbitoView() {
  const params = useSearchParams()
  const router = useRouter()
  const pathname = usePathname()
  const { toast } = useToast()

  const [input, setInput] = useState<ScopeInput>(() => queryToInput(params.toString()) ?? EMPTY_INPUT)
  const [assessment, setAssessment] = useState<ScopeAssessment | null>(() => {
    const fromUrl = queryToInput(params.toString())
    return fromUrl ? assessScope(fromUrl) : null
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
      setAssessment(assessScope(next))
    } else {
      setInput(EMPTY_INPUT)
      setAssessment(null)
    }
  }, [params])

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
      setFormError('Indica dipendenti e ricavi netti, oppure rispondi alle domande sull’IA, poi premi di nuovo Verifica l’ambito.')
      return
    }
    setFormError(undefined)
    setAssessment(assessScope(input))
    const q = inputToQuery(input).toString()
    lastQuery.current = q
    router.replace(`${pathname}?${q}`, { scroll: false })
  }, [input, pathname, router])

  const reset = useCallback(() => {
    setAssessment(null)
    setFormError(undefined)
    lastQuery.current = ''
    router.replace(pathname, { scroll: false })
  }, [pathname, router])

  const loadClient = (id: string) => {
    const c = clients.find((x) => x.id === id)
    if (!c) return
    const country = c.jurisdictions?.find((j) => EU_COUNTRIES.some((e) => e.code === j))
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
    const ok = await copyText(assessmentToText(assessment))
    toast(
      ok
        ? { kind: 'ok', title: 'Copiato' }
        : { kind: 'bad', title: 'Copia non riuscita', description: 'Seleziona il testo del risultato e copialo a mano.' },
    )
  }

  const copyLink = async () => {
    const ok = await copyText(window.location.href)
    toast(
      ok
        ? { kind: 'ok', title: 'Copiato' }
        : { kind: 'bad', title: 'Copia non riuscita', description: 'Copia l’indirizzo dalla barra del browser.' },
    )
  }

  return (
    <div>
      <PageHeader
        title="Ambito"
        description="Quali obblighi si applicano a un’impresa, e da quando, con la norma che lo stabilisce."
        meta={`Regole e date verificate il ${formatDateIt(VERIFIED_ON)}. Primo filtro indicativo, non un parere legale.`}
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
              title="Compila il profilo e premi Verifica l’ambito"
              description="Il risultato mostra, per CSRD, CSDDD e AI Act (art. 50), se l’obbligo si applica, da quando e su quale norma si fonda."
            />
          )}
        </div>
      </div>
    </div>
  )
}
