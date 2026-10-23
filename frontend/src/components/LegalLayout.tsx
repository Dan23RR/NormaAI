import { SiteHeader } from '@/components/site/SiteHeader'
import { SiteFooter } from '@/components/site/SiteFooter'

/**
 * Wrapper for static legal/policy pages: privacy, terms, security, cookie.
 * Same header and footer as the landing, a reading column in the middle.
 */
export function LegalLayout({
  children,
  title,
  intro,
  lastUpdated,
}: {
  children: React.ReactNode
  title: string
  intro?: string
  lastUpdated?: string
}) {
  return (
    <div className="min-h-screen bg-surface text-ink">
      <SiteHeader compact />
      <main className="mx-auto max-w-3xl px-6 py-14">
        <header className="mb-10 border-b border-rule pb-8">
          <h1 className="text-h1 md:text-display">{title}</h1>
          {intro && <p className="mt-4 text-read text-ink-2">{intro}</p>}
          {lastUpdated && <p className="mt-4 text-small text-ink-3">Ultimo aggiornamento: {lastUpdated}</p>}
        </header>
        <article className="space-y-8 text-read text-ink-2 [&_a]:text-union [&_a]:hover:underline [&_li]:mt-1.5 [&_ol]:list-decimal [&_ol]:pl-6 [&_strong]:font-semibold [&_strong]:text-ink [&_ul]:list-disc [&_ul]:pl-6">
          {children}
        </article>
      </main>
      <SiteFooter />
    </div>
  )
}

/** Section with a Literata heading, so page bodies don't repeat classes. */
export function LegalSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="mb-3 text-h3">{title}</h2>
      <div className="space-y-3">{children}</div>
    </section>
  )
}
