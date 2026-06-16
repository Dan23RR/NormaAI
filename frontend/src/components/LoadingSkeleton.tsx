export function LoadingSkeleton({ rows = 3, className = '' }: { rows?: number; className?: string }) {
  return (
    <div className={`animate-pulse space-y-4 ${className}`} role="status" aria-label="Caricamento...">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="space-y-2">
          <div className="h-4 bg-surface2 rounded w-3/4" />
          <div className="h-3 bg-surface2 rounded w-1/2" />
        </div>
      ))}
      <span className="sr-only">Caricamento...</span>
    </div>
  );
}

export function StatSkeleton() {
  return (
    <div className="animate-pulse bg-surface border border-border rounded-xl p-6" role="status" aria-label="Caricamento statistica">
      <div className="h-8 bg-surface2 rounded w-16 mx-auto mb-2" />
      <div className="h-3 bg-surface2 rounded w-20 mx-auto" />
    </div>
  );
}

export function CardSkeleton() {
  return (
    <div className="animate-pulse bg-surface border border-border rounded-xl p-6" role="status" aria-label="Caricamento contenuto">
      <div className="h-3 bg-surface2 rounded w-24 mb-4" />
      <div className="space-y-3">
        <div className="h-4 bg-surface2 rounded w-full" />
        <div className="h-4 bg-surface2 rounded w-5/6" />
        <div className="h-4 bg-surface2 rounded w-2/3" />
      </div>
    </div>
  );
}

export function ChatSkeleton() {
  return (
    <div className="animate-pulse space-y-4 p-4" role="status" aria-label="Caricamento conversazione">
      <div className="flex justify-end">
        <div className="h-10 bg-surface2 rounded-xl w-2/3" />
      </div>
      <div className="flex justify-start">
        <div className="h-20 bg-surface2 rounded-xl w-3/4" />
      </div>
    </div>
  );
}

export function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="animate-pulse" role="status" aria-label="Caricamento tabella">
      <div className="h-10 bg-surface2 rounded-t-lg mb-1" />
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-12 bg-surface2/50 rounded mb-1" />
      ))}
    </div>
  );
}
