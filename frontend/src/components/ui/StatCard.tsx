import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

/** A dated fact with a number: label first, value in Literata, hint below. */
export function StatCard({
  label,
  value,
  hint,
  tone,
  className,
}: {
  label: ReactNode
  value: ReactNode
  hint?: ReactNode
  tone?: 'ok' | 'warn' | 'bad'
  className?: string
}) {
  return (
    <div className={cn('rounded-lg border border-rule bg-surface px-5 py-4', className)}>
      <p className="text-small text-ink-2">{label}</p>
      <p
        className={cn(
          'mt-1 font-serif text-h2 font-medium tabular',
          tone === 'ok' && 'text-ok',
          tone === 'warn' && 'text-warn',
          tone === 'bad' && 'text-bad',
          !tone && 'text-ink',
        )}
      >
        {value}
      </p>
      {hint && <p className="mt-1 text-caption text-ink-3">{hint}</p>}
    </div>
  )
}
