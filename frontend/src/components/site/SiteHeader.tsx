'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { Menu, X } from 'lucide-react'
import { Logo } from '@/components/Logo'
import { ButtonLink } from '@/components/ui/Button'
import { getAccessToken } from '@/lib/auth'
import { cn } from '@/lib/cn'

const links: Array<{ href: string; label: string }> = [
  { href: '/#come-funziona', label: 'Come funziona' },
  { href: '/#fonti', label: 'Fonti' },
  { href: '/metodo', label: 'Metodo' },
  { href: '/#codex', label: 'Codex' },
]

/** Shared header of the public pages. */
export function SiteHeader({ compact }: { compact?: boolean }) {
  const [authed, setAuthed] = useState(false)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    setAuthed(Boolean(getAccessToken()))
  }, [])

  return (
    <header className="sticky top-0 z-30 border-b border-rule bg-surface/90 backdrop-blur">
      <div className="mx-auto flex max-w-site items-center justify-between gap-6 px-6 py-3.5">
        <Logo />
        {!compact && (
          <nav aria-label="Principale" className="hidden items-center gap-6 md:flex">
            {links.map((l) => (
              <Link key={l.href} href={l.href} className="text-body text-ink-2 no-underline hover:text-ink">
                {l.label}
              </Link>
            ))}
          </nav>
        )}
        <div className="hidden items-center gap-2 md:flex">
          {authed ? (
            <ButtonLink href="/app" size="sm">
              Vai all'applicazione
            </ButtonLink>
          ) : (
            <>
              <ButtonLink href="/login" variant="ghost" size="sm">
                Accedi
              </ButtonLink>
              <ButtonLink href="/#demo" size="sm">
                Richiedi una demo
              </ButtonLink>
            </>
          )}
        </div>
        <button
          type="button"
          className="rounded-md p-2 text-ink-2 hover:bg-surface-3 hover:text-ink md:hidden"
          aria-expanded={open}
          aria-controls="site-menu"
          aria-label={open ? 'Chiudi il menu' : 'Apri il menu'}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? <X className="h-5 w-5" aria-hidden="true" /> : <Menu className="h-5 w-5" aria-hidden="true" />}
        </button>
      </div>
      <div id="site-menu" className={cn('border-t border-rule bg-surface px-6 py-4 md:hidden', !open && 'hidden')}>
        <nav aria-label="Principale (mobile)" className="flex flex-col gap-3">
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              onClick={() => setOpen(false)}
              className="text-read text-ink no-underline"
            >
              {l.label}
            </Link>
          ))}
        </nav>
        <div className="mt-4 flex flex-col gap-2">
          {authed ? (
            <ButtonLink href="/app">Vai all'applicazione</ButtonLink>
          ) : (
            <>
              <ButtonLink href="/#demo">Richiedi una demo</ButtonLink>
              <ButtonLink href="/login" variant="secondary">
                Accedi
              </ButtonLink>
            </>
          )}
        </div>
      </div>
    </header>
  )
}
