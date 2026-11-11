'use client'

import type { ReactNode } from 'react'
import { useTranslations } from 'next-intl'
import { cn } from '@/lib/cn'
import type { Failure } from './errors'

/**
 * A failure of the documents API in words: what happened and what to do,
 * then the server's own sentence when it adds something, and the status
 * code for whoever has to report it.
 */
export function FailureMessage({
  failure,
  title,
  action,
  className,
}: {
  failure: Failure
  title?: string
  action?: ReactNode
  className?: string
}) {
  const t = useTranslations('controlla.errors')
  const message = t(failure.kind)
  const detail = failure.detail?.trim()
  return (
    <div role="alert" className={cn('rounded-md border border-bad/30 bg-bad/5 px-4 py-3', className)}>
      {title && <p className="text-body font-medium text-ink">{title}</p>}
      <p className={cn('text-body text-ink', title && 'mt-1')}>{message}</p>
      {detail && detail !== message && <p className="mt-1 break-words text-small text-ink-2">{t('serverDetail', { detail })}</p>}
      {failure.status !== undefined && <p className="mt-1 text-caption tabular text-ink-2">{t('code', { status: String(failure.status) })}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  )
}
