export default function QALoading() {
  return (
    <div className="flex flex-col lg:flex-row gap-4 h-[calc(100vh-8rem)] animate-pulse">
      <div className="flex-1 flex flex-col gap-4">
        <div className="flex-1 bg-surface rounded-xl" />
        <div className="h-12 bg-surface rounded-lg" />
      </div>
      <div className="w-full lg:w-80 h-48 bg-surface rounded-xl" />
    </div>
  )
}
