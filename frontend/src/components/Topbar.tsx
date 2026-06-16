'use client'

import { usePathname } from 'next/navigation'
import { Menu, Globe } from 'lucide-react'
import { useLocale } from '@/hooks/useLocale'

const titles: Record<string, string> = {
  '/dashboard': 'Overview',
  '/dashboard/qa': 'Regulatory Q&A',
  '/dashboard/gap-analysis': 'Gap Analysis',
  '/dashboard/monitor': 'Change Monitor',
  '/dashboard/cross-framework': 'Cross-Framework Intelligence',
  '/dashboard/alerts': 'Alerts',
  '/dashboard/regulatory-feed': 'Regulatory Feed',
  '/dashboard/documents': 'Documents',
  '/dashboard/reports': 'Reports',
  '/dashboard/clients': 'Clients',
  '/dashboard/audit-trail': 'Audit Trail',
  '/dashboard/workflow': 'Workflow',
  '/dashboard/analytics': 'Analytics',
  '/dashboard/admin': 'Administration',
}

interface TopbarProps {
  onMobileMenuOpen: () => void
  sidebarCollapsed: boolean
}

export default function Topbar({ onMobileMenuOpen }: TopbarProps) {
  const pathname = usePathname()
  const { locale, setLocale } = useLocale()
  const title = titles[pathname] || 'Dashboard'

  return (
    <header className="h-14 border-b border-white/[0.06] flex items-center px-4 md:px-6 gap-3 sticky top-0 bg-bg/80 backdrop-blur-sm z-20">
      <button
        onClick={onMobileMenuOpen}
        className="md:hidden p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/[0.04] transition"
        aria-label="Apri menu"
      >
        <Menu size={20} />
      </button>
      <h1 className="text-base font-semibold">{title}</h1>
      <div className="ml-auto flex items-center gap-2">
        <Globe size={14} className="text-slate-500" />
        <select
          value={locale}
          onChange={(e) => setLocale(e.target.value as 'it' | 'en' | 'de')}
          className="bg-transparent text-xs text-slate-400 focus:outline-none cursor-pointer hover:text-white transition"
          aria-label="Seleziona lingua"
        >
          <option value="it">IT</option>
          <option value="en">EN</option>
          <option value="de">DE</option>
        </select>
      </div>
    </header>
  )
}
