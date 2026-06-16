export default function DashboardLoading() {
  return (
    <div className="p-6 space-y-6 animate-pulse" role="status" aria-label="Caricamento dashboard">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="bg-surface border border-border rounded-xl p-6">
            <div className="h-8 bg-surface2 rounded w-16 mx-auto mb-2" />
            <div className="h-3 bg-surface2 rounded w-24 mx-auto" />
          </div>
        ))}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {[1, 2].map((i) => (
          <div key={i} className="bg-surface border border-border rounded-xl p-6">
            <div className="h-3 bg-surface2 rounded w-32 mb-4" />
            <div className="space-y-3">
              <div className="h-4 bg-surface2 rounded w-full" />
              <div className="h-4 bg-surface2 rounded w-5/6" />
              <div className="h-4 bg-surface2 rounded w-4/6" />
            </div>
          </div>
        ))}
      </div>
      <span className="sr-only">Caricamento dashboard in corso...</span>
    </div>
  );
}
