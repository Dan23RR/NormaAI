export default function RegFeedLoading() {
  return (
    <div className="space-y-6 max-w-5xl animate-pulse">
      <div className="h-8 w-48 bg-surface rounded-lg" />
      <div className="flex gap-3">
        <div className="h-10 w-40 bg-surface rounded-lg" />
        <div className="h-10 w-40 bg-surface rounded-lg" />
      </div>
      {[...Array(5)].map((_, i) => (
        <div key={i} className="h-28 bg-surface rounded-xl" />
      ))}
    </div>
  )
}
