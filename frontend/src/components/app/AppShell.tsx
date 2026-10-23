'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useCallback, useEffect, useState, type ReactNode } from 'react'
import {
  MessageSquareText,
  ListChecks,
  CalendarClock,
  Building2,
  FileText,
  Settings,
  ShieldCheck,
  LogOut,
  Menu,
  X,
  PanelLeftClose,
  PanelLeftOpen,
  Sun,
  Moon,
} from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { Logo, LogoMark } from '@/components/Logo'
import { cn } from '@/lib/cn'

export const APP_NAV: Array<{
  href: string
  label: string
  icon: typeof MessageSquareText
  adminOnly?: boolean
}> = [
  { href: '/app/chiedi', label: 'Chiedi', icon: MessageSquareText },
  { href: '/app/ambito', label: 'Ambito', icon: ListChecks },
  { href: '/app/monitoraggio', label: 'Monitoraggio', icon: CalendarClock },
  { href: '/app/clienti', label: 'Clienti', icon: Building2 },
  { href: '/app/report', label: 'Report', icon: FileText },
  { href: '/app/impostazioni', label: 'Impostazioni', icon: Settings },
  { href: '/app/admin', label: 'Amministrazione', icon: ShieldCheck, adminOnly: true },
]

const COLLAPSED_KEY = 'normaai_sidebar_collapsed'
const THEME_KEY = 'normaai.theme'

function useTheme() {
  const [dark, setDark] = useState(false)
  // The class on <html> is the source of truth; Impostazioni toggles it too,
  // so the icon follows the class instead of its own copy of the state.
  useEffect(() => {
    const root = document.documentElement
    const sync = () => setDark(root.classList.contains('dark'))
    sync()
    const observer = new MutationObserver(sync)
    observer.observe(root, { attributes: true, attributeFilter: ['class'] })
    return () => observer.disconnect()
  }, [])
  const toggle = useCallback(() => {
    const next = !document.documentElement.classList.contains('dark')
    document.documentElement.classList.toggle('dark', next)
    try {
      localStorage.setItem(THEME_KEY, next ? 'dark' : 'light')
    } catch {
      /* preference stays for this page only */
    }
  }, [])
  return { dark, toggle }
}

function Initials({ name }: { name?: string }) {
  const letters = (name || '?')
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w.charAt(0).toUpperCase())
    .join('')
  return (
    <span
      aria-hidden="true"
      className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-union/10 text-caption font-semibold text-union"
    >
      {letters}
    </span>
  )
}

/**
 * The application frame: a left rail with the brand, the six surfaces and
 * the organization; the content column with the page itself. The rail
 * collapses on desktop and becomes a drawer on small screens.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname()
  const { user, logout, demoMode } = useAuth()
  const { dark, toggle: toggleTheme } = useTheme()
  const [collapsed, setCollapsed] = useState(false)
  const [drawer, setDrawer] = useState(false)

  useEffect(() => {
    try {
      setCollapsed(localStorage.getItem(COLLAPSED_KEY) === 'true')
    } catch {
      /* default stays expanded */
    }
  }, [])

  useEffect(() => {
    setDrawer(false)
  }, [pathname])

  const toggleCollapsed = () => {
    setCollapsed((v) => {
      const next = !v
      try {
        localStorage.setItem(COLLAPSED_KEY, String(next))
      } catch {
        /* ignore */
      }
      return next
    })
  }

  const nav = (
    <nav aria-label="Sezioni" className="flex-1 overflow-y-auto px-2 py-3">
      <ul className="space-y-0.5">
        {APP_NAV.filter((item) => !item.adminOnly || user?.role === 'admin').map((item) => {
          const active = pathname === item.href || pathname.startsWith(item.href + '/')
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                aria-current={active ? 'page' : undefined}
                title={collapsed ? item.label : undefined}
                className={cn(
                  'flex items-center gap-3 rounded-md px-3 py-2 text-body no-underline transition-colors',
                  collapsed && 'justify-center px-0',
                  active ? 'bg-union/10 font-medium text-union' : 'text-ink-2 hover:bg-surface-3 hover:text-ink',
                )}
              >
                <item.icon className="h-[18px] w-[18px] shrink-0" aria-hidden="true" />
                {!collapsed && <span>{item.label}</span>}
              </Link>
            </li>
          )
        })}
      </ul>
    </nav>
  )

  const railFooter = (
    <div className="border-t border-rule p-2">
      <div className={cn('flex items-center gap-1', collapsed ? 'flex-col' : 'justify-between px-1')}>
        <button
          type="button"
          onClick={toggleTheme}
          className="rounded-md p-2 text-ink-3 hover:bg-surface-3 hover:text-ink"
          aria-label={dark ? 'Passa al tema chiaro' : 'Passa al tema scuro'}
          title={dark ? 'Tema chiaro' : 'Tema scuro'}
        >
          {dark ? <Sun className="h-4 w-4" aria-hidden="true" /> : <Moon className="h-4 w-4" aria-hidden="true" />}
        </button>
        <button
          type="button"
          onClick={toggleCollapsed}
          className="hidden rounded-md p-2 text-ink-3 hover:bg-surface-3 hover:text-ink md:block"
          aria-label={collapsed ? 'Espandi la barra laterale' : 'Comprimi la barra laterale'}
          title={collapsed ? 'Espandi' : 'Comprimi'}
        >
          {collapsed ? (
            <PanelLeftOpen className="h-4 w-4" aria-hidden="true" />
          ) : (
            <PanelLeftClose className="h-4 w-4" aria-hidden="true" />
          )}
        </button>
      </div>
      <div className={cn('mt-1 flex items-center gap-3 rounded-md px-2 py-2', collapsed && 'justify-center px-0')}>
        <Initials name={user?.name} />
        {!collapsed && (
          <div className="min-w-0 flex-1">
            <p className="truncate text-small font-medium text-ink">{user?.name || 'Utente'}</p>
            <p className="truncate text-caption text-ink-3">{user?.organization_name}</p>
          </div>
        )}
        <button
          type="button"
          onClick={logout}
          className={cn('rounded-md p-2 text-ink-3 hover:bg-surface-3 hover:text-bad', collapsed && 'hidden')}
          aria-label="Esci"
          title="Esci"
        >
          <LogOut className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
    </div>
  )

  const rail = (
    <div className="flex h-full flex-col bg-surface">
      <div className={cn('flex h-14 items-center border-b border-rule', collapsed ? 'justify-center' : 'px-4')}>
        {collapsed ? (
          <Link href="/app" aria-label="NormaAI, inizio">
            <LogoMark size={28} />
          </Link>
        ) : (
          <Logo href="/app" />
        )}
      </div>
      {nav}
      {railFooter}
    </div>
  )

  return (
    <div className="min-h-screen bg-canvas">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-union focus:px-4 focus:py-2 focus:text-union-ink"
      >
        Vai al contenuto
      </a>

      {/* Desktop rail */}
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-30 hidden border-r border-rule transition-[width] md:block',
          collapsed ? 'w-rail-collapsed' : 'w-rail',
        )}
      >
        {rail}
      </aside>

      {/* Mobile top bar + drawer */}
      <div className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-rule bg-surface px-4 md:hidden">
        <Logo href="/app" size="sm" />
        <button
          type="button"
          onClick={() => setDrawer(true)}
          className="rounded-md p-2 text-ink-2 hover:bg-surface-3 hover:text-ink"
          aria-label="Apri il menu"
          aria-expanded={drawer}
        >
          <Menu className="h-5 w-5" aria-hidden="true" />
        </button>
      </div>
      {drawer && (
        <div className="fixed inset-0 z-40 md:hidden" role="dialog" aria-modal="true" aria-label="Menu">
          <div className="absolute inset-0 bg-[#0C1B33]/50" onClick={() => setDrawer(false)} aria-hidden="true" />
          <div className="absolute inset-y-0 left-0 w-rail border-r border-rule shadow-pop">
            {rail}
            <button
              type="button"
              onClick={() => setDrawer(false)}
              className="absolute right-2 top-3 rounded-md p-2 text-ink-3 hover:bg-surface-3 hover:text-ink"
              aria-label="Chiudi il menu"
            >
              <X className="h-5 w-5" aria-hidden="true" />
            </button>
          </div>
        </div>
      )}

      <div className={cn('flex min-h-screen flex-col transition-[padding]', collapsed ? 'md:pl-rail-collapsed' : 'md:pl-rail')}>
        {demoMode && (
          <div className="border-b border-mark-deep/40 bg-mark/30 px-4 py-2 text-small text-[#0C1B33] md:px-8">
            Demo con dati di esempio: le risposte e i clienti non vengono dal corpus reale.{' '}
            <button type="button" onClick={logout} className="font-medium underline underline-offset-4">
              Esci dalla demo
            </button>
          </div>
        )}
        <main id="main-content" className="mx-auto w-full max-w-app flex-1 px-4 py-6 md:px-8 md:py-8">
          {children}
        </main>
        <footer className="px-4 py-4 md:px-8">
          <p className="max-w-prose text-caption text-ink-3">
            NormaAI usa un sistema di intelligenza artificiale per generare le risposte (Regolamento (UE)
            2024/1689, art. 50). Le risposte non sostituiscono la consulenza di un professionista.{' '}
            <Link href="/terms" className="underline">
              Termini
            </Link>
            {', '}
            <Link href="/privacy" className="underline">
              Privacy
            </Link>
            .
          </p>
        </footer>
      </div>
    </div>
  )
}
