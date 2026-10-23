import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

/** An empty screen is an invitation to act: say what to do, offer the action. */
export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: ReactNode
  title: ReactNode
  description?: ReactNode
  action?: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        'flex flex-col items-center rounded-lg border border-rule bg-surface px-6 py-12 text-center',
        className,
      )}
    >
      {icon && <div className="mb-4 text-ink-3">{icon}</div>}
      <h3 className="text-h3">{title}</h3>
      {description && <p className="mt-2 max-w-md text-body text-ink-2">{description}</p>}
      {action && <div className="mt-6">{action}</div>}
    </div>
  )
}
