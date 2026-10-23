import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

export function PageHeader({
  title,
  description,
  actions,
  meta,
  className,
}: {
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
  /** Dated facts that frame the page: corpus date, last verification. */
  meta?: ReactNode
  className?: string
}) {
  return (
    <header className={cn('mb-6 border-b border-rule pb-5', className)}>
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div className="min-w-0 max-w-prose">
          <h1 className="text-h2 md:text-h1">{title}</h1>
          {description && <p className="mt-2 text-body text-ink-2">{description}</p>}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {meta && <div className="mt-3 text-caption text-ink-3">{meta}</div>}
    </header>
  )
}
