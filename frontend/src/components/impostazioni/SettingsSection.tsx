import type { ReactNode } from 'react'

/** One section of the settings page: heading and description on the left, content on the right. */
export function SettingsSection({
  id,
  title,
  description,
  children,
}: {
  id: string
  title: string
  description?: ReactNode
  children: ReactNode
}) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="border-t border-rule py-8 first:border-t-0 first:pt-0">
      <div className="grid gap-5 md:grid-cols-[240px_minmax(0,1fr)] md:gap-10">
        <div>
          <h2 id={`${id}-title`} className="text-h3">
            {title}
          </h2>
          {description && <p className="mt-1 text-small text-ink-2">{description}</p>}
        </div>
        <div className="min-w-0 max-w-2xl">{children}</div>
      </div>
    </section>
  )
}

export function SettingsRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-1 py-3 sm:grid-cols-[160px_1fr] sm:gap-6">
      <dt className="text-small text-ink-2">{label}</dt>
      <dd className="text-body text-ink">{children}</dd>
    </div>
  )
}
