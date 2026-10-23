'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { useTranslations } from 'next-intl'
import { Menu, X } from 'lucide-react'
import { Logo } from '@/components/Logo'
import { ButtonLink } from '@/components/ui/Button'
import { getAccessToken } from '@/lib/auth'
import { cn } from '@/lib/cn'

const LINKS = [
  { href: '/#come-funziona', key: 'howItWorks' },
  { href: '/#fonti', key: 'sources' },
  { href: '/metodo', key: 'method' },
  { href: '/#codex', key: 'codex' },
] as const

/** Shared header of the public pages. */
export function SiteHeader({ compact }: { compact?: boolean }) {
  const t = useTranslations('site.header')
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
          <nav aria-label={t('nav')} className="hidden items-center gap-6 md:flex">
            {LINKS.map((l) => (
              <Link key={l.href} href={l.href} className="text-body text-ink-2 no-underline hover:text-ink">
                {t(l.key)}
              </Link>
            ))}
          </nav>
        )}
        <div className="hidden items-center gap-2 md:flex">
          {authed ? (
            <ButtonLink href="/app" size="sm">
              {t('openApp')}
            </ButtonLink>
          ) : (
            <>
              <ButtonLink href="/login" variant="ghost" size="sm">
                {t('signIn')}
              </ButtonLink>
              <ButtonLink href="/#demo" size="sm">
                {t('requestDemo')}
              </ButtonLink>
            </>
          )}
        </div>
        <button
          type="button"
          className="rounded-md p-2 text-ink-2 hover:bg-surface-3 hover:text-ink md:hidden"
          aria-expanded={open}
          aria-controls="site-menu"
          aria-label={open ? t('closeMenu') : t('openMenu')}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? <X className="h-5 w-5" aria-hidden="true" /> : <Menu className="h-5 w-5" aria-hidden="true" />}
        </button>
      </div>
      <div id="site-menu" className={cn('border-t border-rule bg-surface px-6 py-4 md:hidden', !open && 'hidden')}>
        <nav aria-label={t('navMobile')} className="flex flex-col gap-3">
          {LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              onClick={() => setOpen(false)}
              className="text-read text-ink no-underline"
            >
              {t(l.key)}
            </Link>
          ))}
        </nav>
        <div className="mt-4 flex flex-col gap-2">
          {authed ? (
            <ButtonLink href="/app">{t('openApp')}</ButtonLink>
          ) : (
            <>
              <ButtonLink href="/#demo">{t('requestDemo')}</ButtonLink>
              <ButtonLink href="/login" variant="secondary">
                {t('signIn')}
              </ButtonLink>
            </>
          )}
        </div>
      </div>
    </header>
  )
}
