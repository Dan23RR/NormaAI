export default function AnalyticsLoading() {
  return (
    <div className="space-y-6 max-w-5xl animate-pulse">
      <div className="h-8 w-32 bg-surface rounded-lg" />
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-64 bg-surface rounded-xl" />
        ))}
      </div>
    </div>
  )
}
