'use client'

import { useEffect, useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/hooks/useAuth'
import Sidebar from '@/components/Sidebar'
import Topbar from '@/components/Topbar'
import { ErrorBoundary } from '@/components/ErrorBoundary'

const SIDEBAR_COLLAPSED_KEY = 'normaai_sidebar_collapsed'

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  const router = useRouter()

  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    if (typeof window === 'undefined') return false
    return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === 'true'
  })
  const [mobileOpen, setMobileOpen] = useState(false)

  const toggleSidebar = useCallback(() => {
    setSidebarCollapsed((prev) => {
      const next = !prev
      localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(next))
      return next
    })
  }, [])

  const openMobile = useCallback(() => setMobileOpen(true), [])
  const closeMobile = useCallback(() => setMobileOpen(false), [])

  useEffect(() => {
    if (!loading && !user) {
      router.replace('/login')
    }
  }, [user, loading, router])

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen" role="status" aria-label="Caricamento">
        <div className="w-6 h-6 border-2 border-accent border-t-transparent rounded-full animate-spin" />
        <span className="sr-only">Caricamento...</span>
      </div>
    )
  }

  if (!user) return null

  return (
    <div className="flex min-h-screen">
      <a href="#main-content" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:top-4 focus:left-4 focus:px-4 focus:py-2 focus:bg-accent focus:text-white focus:rounded-lg focus:text-sm focus:font-medium">
        Vai al contenuto principale
      </a>
      <Sidebar
        collapsed={sidebarCollapsed}
        onToggle={toggleSidebar}
        mobileOpen={mobileOpen}
        onMobileClose={closeMobile}
      />
      <div
        className={`flex-1 flex flex-col transition-[margin] duration-200 ${
          sidebarCollapsed ? 'md:ml-16' : 'md:ml-60'
        }`}
      >
        <Topbar onMobileMenuOpen={openMobile} sidebarCollapsed={sidebarCollapsed} />
        <main id="main-content" className="flex-1 p-4 md:p-6">
          <ErrorBoundary>{children}</ErrorBoundary>
        </main>
        <footer className="px-4 md:px-6 py-3 border-t border-white/[0.04]" role="contentinfo">
          <div className="flex items-start gap-3 max-w-5xl">
            <span className="shrink-0 text-[9px] px-1.5 py-0.5 rounded border border-blue-400/20 bg-blue-400/5 text-blue-400 font-medium mt-0.5">
              AI Act Art. 50
            </span>
            <p className="text-[10px] text-slate-600 leading-relaxed">
              NormaAI utilizza intelligenza artificiale (AI) per analizzare testi normativi e generare risposte.
              Le informazioni fornite hanno scopo esclusivamente informativo e di supporto decisionale.
              <strong className="text-slate-500"> Non costituiscono consulenza legale, fiscale o professionale.</strong>
              {' '}Per decisioni vincolanti consultare sempre un professionista qualificato.
              I punteggi di conformità sono stime qualitative, non certificazioni.
              {' '}<a href="/terms" className="underline hover:text-slate-400 transition">Termini di Servizio</a>
              {' · '}<a href="/privacy" className="underline hover:text-slate-400 transition">Privacy Policy</a>
              {' · '}<a href="/security" className="underline hover:text-slate-400 transition">Security</a>
            </p>
          </div>
        </footer>
      </div>
    </div>
  )
}
