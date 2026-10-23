import type { ReactNode } from 'react'
import { useTranslations } from 'next-intl'
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
  children: ReactNode
  title: string
  intro?: string
  /** Already formatted for the reader, e.g. "23 ottobre 2026". */
  lastUpdated?: string
}) {
  const t = useTranslations('legal')
  return (
    <div className="min-h-screen bg-surface text-ink">
      <SiteHeader compact />
      <main className="mx-auto max-w-3xl px-6 py-14">
        <header className="mb-10 border-b border-rule pb-8">
          <h1 className="text-h1 md:text-display">{title}</h1>
          {intro && <p className="mt-4 text-read text-ink-2">{intro}</p>}
          {lastUpdated && <p className="mt-4 text-small text-ink-3">{t('lastUpdated', { date: lastUpdated })}</p>}
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
export function LegalSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h2 className="mb-3 text-h3">{title}</h2>
      <div className="space-y-3">{children}</div>
    </section>
  )
}

/** The tags the legal texts use inside their paragraphs (`t.rich`). */
export const LEGAL_TAGS = {
  strong: (chunks: ReactNode) => <strong>{chunks}</strong>,
  code: (chunks: ReactNode) => <code className="font-mono">{chunks}</code>,
  mail: (chunks: ReactNode) => <a href="mailto:info@normaai.org">{chunks}</a>,
  security: (chunks: ReactNode) => <a href="mailto:info@normaai.org?subject=%5BSECURITY%5D%20NormaAI">{chunks}</a>,
  privacy: (chunks: ReactNode) => <a href="/privacy">{chunks}</a>,
  cookie: (chunks: ReactNode) => <a href="/cookie">{chunks}</a>,
  securityPage: (chunks: ReactNode) => <a href="/security">{chunks}</a>,
  github: (chunks: ReactNode) => (
    <a href="https://github.com/Dan23RR/NormaAI" target="_blank" rel="noopener noreferrer">
      {chunks}
    </a>
  ),
}

/** The numbered keys of a message object ("1", "2", ...), in order. */
export function itemKeys(raw: unknown): string[] {
  if (!raw || typeof raw !== 'object') return []
  return Object.keys(raw as Record<string, unknown>).sort((a, b) => Number(a) - Number(b))
}
