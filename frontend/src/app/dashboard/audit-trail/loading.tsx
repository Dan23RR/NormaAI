export default function AuditTrailLoading() {
  return (
    <div className="space-y-6 max-w-6xl animate-pulse">
      <div className="flex justify-between">
        <div className="h-8 w-32 bg-surface rounded-lg" />
        <div className="h-10 w-28 bg-surface rounded-lg" />
      </div>
      <div className="flex gap-3">
        <div className="h-10 flex-1 bg-surface rounded-lg" />
        <div className="h-10 w-40 bg-surface rounded-lg" />
        <div className="h-10 w-40 bg-surface rounded-lg" />
      </div>
      <div className="bg-surface rounded-xl h-96" />
    </div>
  )
}
