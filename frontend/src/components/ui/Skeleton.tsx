import { cn } from '@/lib/cn'

export function Skeleton({ className, label = 'Caricamento' }: { className?: string; label?: string }) {
  return (
    <div className={cn('animate-pulse rounded-md bg-surface-3', className)} role="status" aria-label={label}>
      <span className="sr-only">{label}</span>
    </div>
  )
}

export function SkeletonText({ lines = 3, className }: { lines?: number; className?: string }) {
  const widths = ['w-full', 'w-11/12', 'w-4/5', 'w-2/3']
  return (
    <div className={cn('space-y-2', className)} role="status" aria-label="Caricamento">
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className={cn('h-3.5 animate-pulse rounded-sm bg-surface-3', widths[i % widths.length])} />
      ))}
      <span className="sr-only">Caricamento</span>
    </div>
  )
}
