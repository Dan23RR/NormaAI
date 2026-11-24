'use client'

import { useCallback, useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { ArrowLeft, FileText, Info, RefreshCw, Trash2 } from 'lucide-react'
import { Button, ButtonLink } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { PageHeader } from '@/components/ui/PageHeader'
import { Skeleton } from '@/components/ui/Skeleton'
import { useToast } from '@/components/ui/Toast'
import { fetchClient } from '@/components/clienti/clients-api'
import { useAuth } from '@/hooks/useAuth'
import { useDateFormat } from '@/i18n/useDateFormat'
import { CheckFacts, DependenciesList, ReviewNotice, type ClientLink } from './CheckMargin'
import { DeleteCheckDialog } from './DeleteCheckDialog'
import { fetchCheck, recallCheck, recheck } from './documents-api'
import { describeFailure, isMissingCheck, type Failure } from './errors'
import { FailureMessage } from './FailureMessage'
import { FindingCard, FindingRow } from './FindingItem'
import { GroupSummary, groupAnchor } from './GroupSummary'
import { totalFindings } from './labels'
import { ReportDialog } from './ReportDialog'
import { GROUPS, dependencyOf, findingsOf, type DocumentCheck, type FindingGroup } from './types'

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; failure: Failure }
  | { status: 'missing' }
  | { status: 'ready'; check: DocumentCheck; example: boolean }

/** The groups that ask for attention are shown in full; the others one line per reference. */
const IN_FULL: Record<FindingGroup, boolean> = { correggere: true, controllare: true, a_posto: false, non_coperto: false }

function DemoNote({ children }: { children: string }) {
  return (
    <p className="mb-6 flex items-start gap-2 rounded-md border border-rule bg-surface px-4 py-2.5 text-small text-ink-2">
      <Info className="mt-0.5 h-4 w-4 shrink-0 text-union" aria-hidden="true" />
      <span>{children}</span>
    </p>
  )
}

/** One checked document: the outcome by group, every finding, and what is kept of the document. */
export function CheckDetailPage() {
  const t = useTranslations('controlla')
  const tu = useTranslations('ui')
  const params = useParams<{ id: string }>()
  const router = useRouter()
  const { demoMode } = useAuth()
  const { toast } = useToast()
  const formatDate = useDateFormat()
  const id = typeof params?.id === 'string' ? decodeURIComponent(params.id) : ''

  const [state, setState] = useState<LoadState>({ status: 'loading' })
  const [client, setClient] = useState<ClientLink>({ state: 'none' })
  const [rechecking, setRechecking] = useState(false)
  const [recheckFailure, setRecheckFailure] = useState<Failure | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [reportOpen, setReportOpen] = useState(false)

  const load = useCallback(async () => {
    if (!id) return
    // The form hands over the check it just received: no second request for it.
    const fresh = recallCheck(id)
    if (fresh) {
      setState({ status: 'ready', check: fresh.check, example: fresh.example })
      return
    }
    setState({ status: 'loading' })
    try {
      setState({ status: 'ready', check: await fetchCheck(id), example: false })
    } catch (err) {
      setState(isMissingCheck(err) ? { status: 'missing' } : { status: 'error', failure: describeFailure(err) })
    }
  }, [id])

  useEffect(() => {
    void load()
  }, [load])

  const clientId = state.status === 'ready' ? state.check.client_id : null
  useEffect(() => {
    if (!clientId) {
      setClient({ state: 'none' })
      return
    }
    let alive = true
    setClient({ state: 'loading' })
    fetchClient(clientId)
      .then((found) => {
        if (alive) setClient(found ? { state: 'found', id: found.id, name: found.name } : { state: 'gone' })
      })
      .catch(() => {
        if (alive) setClient({ state: 'gone' })
      })
    return () => {
      alive = false
    }
  }, [clientId])

  const back = (
    <ButtonLink href="/app/controlla" variant="ghost" size="sm" iconLeft={<ArrowLeft className="h-4 w-4" aria-hidden="true" />}>
      {t('detail.back')}
    </ButtonLink>
  )

  if (state.status === 'loading') {
    return (
      <div>
        <div className="mb-4">{back}</div>
        <div className="space-y-3" role="status" aria-label={t('detail.loading')}>
          <Skeleton className="h-9 w-80 max-w-full" label={t('detail.loading')} />
          <Skeleton className="h-5 w-56" label={t('detail.loading')} />
          <Skeleton className="mt-6 h-20" label={t('detail.loading')} />
          <Skeleton className="h-64" label={t('detail.loading')} />
        </div>
      </div>
    )
  }

  if (state.status === 'error') {
    return (
      <div>
        <div className="mb-4">{back}</div>
        <FailureMessage
          failure={state.failure}
          title={t('detail.loadFailedTitle')}
          action={
            <Button variant="secondary" onClick={load}>
              {tu('retryLoad')}
            </Button>
          }
        />
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
          action={<ButtonLink href="/app/controlla">{t('detail.goToList')}</ButtonLink>}
        />
      </div>
    )
  }

  const { check, example } = state
  const setting = { checkedAt: check.checked_at, lang: check.lang }
  const checked = check.checked_at ? formatDate(check.checked_at) : tu('notAvailable')
  const meta = check.document_date
    ? t('detail.metaWithDate', { checked, date: formatDate(check.document_date) })
    : t('detail.metaNoDate', { checked })

  const runRecheck = async () => {
    setRechecking(true)
    setRecheckFailure(null)
    try {
      const updated = await recheck(check.id)
      setState({ status: 'ready', check: updated, example: false })
      const total = updated.dependencies.length
      const changed = updated.dependencies.filter((d) => d.state === 'changed' || d.state === 'removed').length
      const unavailable = updated.dependencies.filter((d) => d.state === 'unavailable').length
      const lines = [
        total === 0
          ? t('detail.recheckNone')
          : changed > 0
            ? t('detail.recheckChanged', { count: changed })
            : unavailable < total
              ? t('detail.recheckUnchanged', { count: total - unavailable })
              : '',
        unavailable > 0 ? t('detail.recheckUnavailable', { count: unavailable }) : '',
        demoMode ? t('demo.recheck') : '',
      ].filter(Boolean)
      toast({ kind: changed > 0 || unavailable > 0 ? 'neutral' : 'ok', title: t('detail.recheckDoneTitle'), description: lines.join(' ') })
    } catch (err) {
      setRecheckFailure(describeFailure(err))
    } finally {
      setRechecking(false)
    }
  }

  return (
    <div>
      <div className="mb-4">{back}</div>
      <PageHeader
        title={<span className="break-words">{check.filename || t('detailTitle')}</span>}
        meta={meta}
        actions={
          <>
            <Button
              variant="secondary"
              onClick={runRecheck}
              loading={rechecking}
              title={t('detail.recheckHelp')}
              iconLeft={<RefreshCw className="h-4 w-4" aria-hidden="true" />}
            >
              {rechecking ? t('detail.rechecking') : t('detail.recheck')}
            </Button>
            <Button variant="secondary" onClick={() => setReportOpen(true)} iconLeft={<FileText className="h-4 w-4" aria-hidden="true" />}>
              {t('detail.report')}
            </Button>
            <Button variant="danger" onClick={() => setDeleting(true)} iconLeft={<Trash2 className="h-4 w-4" aria-hidden="true" />}>
              {t('detail.delete')}
            </Button>
          </>
        }
      />

      {demoMode && <DemoNote>{example ? t('demo.afterUpload') : t('demo.detail')}</DemoNote>}

      {recheckFailure && (
        <FailureMessage failure={recheckFailure} title={t('detail.recheckFailedTitle')} className="mb-6" />
      )}

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0 max-w-prose space-y-8">
          {check.needs_review && <ReviewNotice check={check} />}

          <GroupSummary counts={check.counts} />

          {totalFindings(check.counts) === 0 && check.findings.length === 0 ? (
            <EmptyState title={t('detail.noFindingsTitle')} description={t('detail.noFindingsDescription')} />
          ) : (
            GROUPS.map((group) => {
              const findings = findingsOf(check, group)
              if (findings.length === 0) return null
              const headingId = `${groupAnchor(group)}-titolo`
              const Item = IN_FULL[group] ? FindingCard : FindingRow
              return (
                <section key={group} id={groupAnchor(group)} aria-labelledby={headingId} className="scroll-mt-6">
                  <h2 id={headingId} className="text-h3">
                    {t('groups.heading', { label: t(`groups.${group}.label`), count: findings.length })}
                  </h2>
                  <p className="mt-1 text-small text-ink-2">{t(`groups.${group}.description`)}</p>
                  <ul className="mt-4 divide-y divide-rule border-y border-rule">
                    {findings.map((finding) => (
                      <li key={finding.id} className={IN_FULL[group] ? 'py-5' : 'py-2.5'}>
                        <Item finding={finding} dependency={dependencyOf(check, finding)} {...setting} />
                      </li>
                    ))}
                  </ul>
                </section>
              )
            })
          )}

          <p className="text-caption text-ink-2">{t('detail.limits')}</p>
        </div>

        <aside aria-label={t('facts.title')} className="min-w-0">
          <div className="flex flex-col gap-8 lg:sticky lg:top-6 lg:max-h-[calc(100vh-3rem)] lg:overflow-y-auto lg:pr-1">
            <CheckFacts check={check} client={client} />
            <DependenciesList check={check} />
          </div>
        </aside>
      </div>

      {deleting && (
        <DeleteCheckDialog open onClose={() => setDeleting(false)} check={check} onDeleted={() => router.push('/app/controlla')} />
      )}
      {reportOpen && <ReportDialog open onClose={() => setReportOpen(false)} check={check} />}
    </div>
  )
}
