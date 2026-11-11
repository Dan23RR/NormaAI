'use client'

import { useCallback, useEffect, useState } from 'react'
import { useTranslations } from 'next-intl'
import { Download } from 'lucide-react'
import { Button, Spinner } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { downloadBlob } from '@/components/report/report-api'
import { fetchReportHtml } from './documents-api'
import { describeFailure, type Failure } from './errors'
import { FailureMessage } from './FailureMessage'
import type { CheckSummary } from './types'

type State = { status: 'loading' } | { status: 'error'; failure: Failure } | { status: 'ready'; html: string }

/**
 * Links of the report open in a new tab: the frame that shows it may not
 * navigate, and EUR-Lex does not let itself be framed anyway.
 */
export function withLinksInNewTab(html: string): string {
  const base = '<base target="_blank">'
  return /<head[^>]*>/i.test(html) ? html.replace(/<head[^>]*>/i, (head) => head + base) : base + html
}

/** "Policy uso IA.pdf" -> "Policy uso IA.controllo.html": the name of the downloaded report. */
export function reportFilename(filename: string, suffix: string): string {
  const stem = filename.replace(/\.[A-Za-z0-9]{1,5}$/, '').replace(/[\\/:*?"<>|]+/g, '_').trim() || 'report'
  return `${stem}.${suffix}.html`
}

/**
 * The HTML report of a check, shown inside the page and offered as a file.
 * The page comes from the server and carries words of the document, so it
 * is shown in a sandboxed frame: no script of it can run, and it cannot
 * reach the session of the application.
 */
export function ReportDialog({
  open,
  onClose,
  check,
}: {
  open: boolean
  onClose: () => void
  check: Pick<CheckSummary, 'id' | 'filename'>
}) {
  const t = useTranslations('controlla.report')
  const tu = useTranslations('ui')
  const [state, setState] = useState<State>({ status: 'loading' })

  const load = useCallback(async () => {
    setState({ status: 'loading' })
    try {
      setState({ status: 'ready', html: await fetchReportHtml(check.id) })
    } catch (err) {
      setState({ status: 'error', failure: describeFailure(err) })
    }
  }, [check.id])

  useEffect(() => {
    if (open) void load()
  }, [open, load])

  const download = () => {
    if (state.status !== 'ready') return
    downloadBlob(new Blob([state.html], { type: 'text/html;charset=utf-8' }), reportFilename(check.filename, t('fileSuffix')))
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={t('title')}
      description={t('description')}
      size="lg"
      footer={
        <>
          <Button type="button" variant="secondary" onClick={onClose}>
            {tu('close')}
          </Button>
          <Button
            type="button"
            onClick={download}
            disabled={state.status !== 'ready'}
            iconLeft={<Download className="h-4 w-4" aria-hidden="true" />}
          >
            {t('download')}
          </Button>
        </>
      }
    >
      {state.status === 'loading' && (
        <p className="flex items-center gap-2 py-10 text-small text-ink-2" role="status">
          <Spinner className="h-4 w-4 text-union" />
          {t('loading')}
        </p>
      )}
      {state.status === 'error' && (
        <FailureMessage
          failure={state.failure}
          title={t('failedTitle')}
          action={
            <Button type="button" variant="secondary" size="sm" onClick={load}>
              {tu('retryLoad')}
            </Button>
          }
        />
      )}
      {state.status === 'ready' && open && (
        <iframe
          title={t('frameTitle', { name: check.filename })}
          sandbox="allow-popups allow-popups-to-escape-sandbox"
          referrerPolicy="no-referrer"
          srcDoc={withLinksInNewTab(state.html)}
          className="h-[60vh] w-full rounded-md border border-rule bg-white"
        />
      )}
    </Dialog>
  )
}
