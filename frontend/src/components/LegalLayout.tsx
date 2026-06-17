'use client'

import Link from 'next/link'
import { useEffect } from 'react'
import { ArrowLeft } from 'lucide-react'

/**
 * Wrapper for static legal/policy pages: privacy, terms, security.
 * Warm-paper editorial theme - visually continuous with the landing.
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
  useEffect(() => {
    document.body.classList.add('paper-bg')
    return () => document.body.classList.remove('paper-bg')
  }, [])

  return (
    <div className="min-h-screen bg-paper text-night">
      {/* Header - same shape as landing nav for visual continuity */}
      <nav className="sticky top-0 z-30 border-b border-line bg-paper/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <Link href="/" className="flex items-center gap-2.5 transition hover:opacity-90">
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-night font-serif text-lg text-paper">
              N
            </div>
            <span className="font-serif text-xl tracking-tight">NormaAI</span>
          </Link>
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 text-sm text-night-2 transition hover:text-night"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Torna alla home
          </Link>
        </div>
      </nav>

      {/* Page content */}
      <main className="mx-auto max-w-3xl px-6 py-14">
        <header className="mb-10 border-b border-line pb-8">
          <h1 className="font-serif text-3xl font-normal tracking-tight md:text-4xl">{title}</h1>
          {intro && (
            <p className="mt-4 leading-relaxed text-night-2">
              {intro}
            </p>
          )}
          {lastUpdated && (
            <p className="mt-4 font-mono text-xs text-night-3">
              Ultimo aggiornamento: {lastUpdated}
            </p>
          )}
        </header>

        <article className="space-y-8 text-sm leading-relaxed text-night-2">
          {children}
        </article>
      </main>

      {/* Footer - minimal, mirrors landing footer */}
      <footer className="border-t border-line bg-paper-2">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-6 py-8 text-xs text-night-3 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-2">
            <div className="flex h-5 w-5 items-center justify-center rounded bg-night font-serif text-[10px] text-paper">
              N
            </div>
            <span>NormaAI © {new Date().getFullYear()}</span>
          </div>
          <div className="flex flex-wrap gap-4">
            <Link href="/privacy" className="transition hover:text-night">Privacy</Link>
            <Link href="/cookie" className="transition hover:text-night">Cookie</Link>
            <Link href="/terms" className="transition hover:text-night">Termini</Link>
            <Link href="/security" className="transition hover:text-night">Sicurezza</Link>
            <a href="mailto:info@normaai.org" className="transition hover:text-night">Contatti</a>
          </div>
        </div>
      </footer>
    </div>
  )
}

/**
 * Small typographic primitives so the page bodies don't repeat
 * the same Tailwind class strings.
 */
export function LegalSection({
  title,
  children,
}: {
  title: string
  children: React.ReactNode
}) {
  return (
    <section>
      <h2 className="mb-3 font-serif text-lg text-night">{title}</h2>
      <div className="space-y-3">{children}</div>
    </section>
  )
}
