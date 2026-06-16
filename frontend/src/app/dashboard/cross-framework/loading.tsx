export default function CrossFrameworkLoading() {
  return (
    <div className="space-y-6 max-w-6xl animate-pulse">
      <div className="h-8 w-64 bg-surface rounded-lg" />
      <div className="bg-surface rounded-xl h-72" />
      {[...Array(3)].map((_, i) => (
        <div key={i} className="h-20 bg-surface rounded-xl" />
      ))}
    </div>
  )
}
