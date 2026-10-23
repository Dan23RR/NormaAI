import { Skeleton, SkeletonText } from '@/components/ui/Skeleton'

// Thin wrappers kept for the pages that still import these names.
// New code uses Skeleton / SkeletonText from '@/components/ui' directly.

export function LoadingSkeleton({ rows = 3, className = '' }: { rows?: number; className?: string }) {
  return <SkeletonText lines={rows} className={className} />
}

export function StatSkeleton() {
  return (
    <div className="rounded-lg border border-rule bg-surface px-5 py-4" role="status" aria-label="Caricamento">
      <Skeleton className="h-3.5 w-24" />
      <Skeleton className="mt-3 h-7 w-16" />
    </div>
  )
}

export function CardSkeleton() {
  return (
    <div className="rounded-lg border border-rule bg-surface p-5" role="status" aria-label="Caricamento">
      <Skeleton className="mb-4 h-3.5 w-32" />
      <SkeletonText lines={3} />
    </div>
  )
}

export function ChatSkeleton() {
  return (
    <div className="space-y-4 p-4" role="status" aria-label="Caricamento della conversazione">
      <div className="flex justify-end">
        <Skeleton className="h-10 w-2/3" />
      </div>
      <div className="flex justify-start">
        <Skeleton className="h-20 w-3/4" />
      </div>
    </div>
  )
}

export function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="overflow-hidden rounded-lg border border-rule bg-surface" role="status" aria-label="Caricamento della tabella">
      <Skeleton className="h-10 rounded-none" />
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="border-t border-rule px-4 py-3">
          <Skeleton className="h-4 w-full" />
        </div>
      ))}
    </div>
  )
}
