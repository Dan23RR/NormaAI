export default function WorkflowLoading() {
  return (
    <div className="space-y-6 max-w-5xl animate-pulse">
      <div className="h-8 w-40 bg-surface rounded-lg" />
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-20 bg-surface rounded-xl" />
        ))}
      </div>
      {[...Array(3)].map((_, i) => (
        <div key={i} className="h-36 bg-surface rounded-xl" />
      ))}
    </div>
  )
}
