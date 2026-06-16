'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useAuth } from '@/hooks/useAuth'
import {
  LayoutDashboard,
  MessageSquare,
  ClipboardCheck,
  Bell,
  BarChart3,
  Shield,
  LogOut,
  X,
  ChevronLeft,
  ChevronRight,
  FileText,
  Building2,
  Upload,
  MessageCircle,
  Database,
  FileSearch,
  GitPullRequest,
  Layers,
  Rss,
} from 'lucide-react'
import { KNOWLEDGE_BASE_META } from '@/lib/mock-data'

const navItems = [
  { href: '/dashboard', label: 'Overview', icon: LayoutDashboard },
  { href: '/dashboard/qa', label: 'Q&A', icon: MessageSquare, section: 'Intelligence' },
  { href: '/dashboard/gap-analysis', label: 'Gap Analysis', icon: ClipboardCheck },
  { href: '/dashboard/monitor', label: 'Monitor', icon: Bell },
  { href: '/dashboard/cross-framework', label: 'Cross-Framework', icon: Layers },
  { href: '/dashboard/alerts', label: 'Alerts', icon: Bell },
  { href: '/dashboard/regulatory-feed', label: 'Reg. Feed', icon: Rss },
  { href: '/dashboard/documents', label: 'Documents', icon: Upload, section: 'Data' },
  { href: '/dashboard/reports', label: 'Reports', icon: FileText },
  { href: '/dashboard/clients', label: 'Clients', icon: Building2, section: 'Management' },
  { href: '/dashboard/audit-trail', label: 'Audit Trail', icon: FileSearch },
  { href: '/dashboard/workflow', label: 'Workflow', icon: GitPullRequest },
  { href: '/dashboard/analytics', label: 'Analytics', icon: BarChart3, section: 'Insights' },
  { href: '/dashboard/admin', label: 'Admin', icon: Shield, adminOnly: true },
]

interface SidebarProps {
  collapsed: boolean
  onToggle: () => void
  mobileOpen: boolean
  onMobileClose: () => void
}

export default function Sidebar({ collapsed, onToggle, mobileOpen, onMobileClose }: SidebarProps) {
  const pathname = usePathname()
  const { user, logout, demoMode } = useAuth()

  let lastSection = ''

  const sidebarContent = (
    <aside
      className={`h-screen bg-surface border-r border-white/[0.06] flex flex-col transition-all duration-200 ${
        collapsed ? 'w-16' : 'w-60'
      }`}
      role="navigation"
      aria-label="Navigazione principale"
    >
      {/* Logo */}
      <div className="px-3 py-5 flex items-center gap-3 border-b border-white/[0.06]">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-accent to-accent2 flex items-center justify-center text-white font-extrabold text-sm flex-shrink-0">
          N
        </div>
        {!collapsed && (
          <>
            <span className="text-base font-semibold tracking-tight">
              NormaAI
            </span>
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-accent/10 text-accent font-medium ml-auto">
              v0.3
            </span>
          </>
        )}
      </div>

      {/* Demo badge */}
      {demoMode && !collapsed && (
        <div className="mx-3 mt-3 px-3 py-1.5 rounded-lg bg-green-500/10 border border-green-500/20 text-green-400 text-[11px] font-medium text-center">
          Demo Mode
        </div>
      )}

      {/* Nav */}
      <nav className="flex-1 px-2 py-4 space-y-0.5 overflow-y-auto">
        {navItems.map((item) => {
          if (item.adminOnly && user?.role !== 'admin') return null

          const isActive = pathname === item.href
          const showSection = item.section && item.section !== lastSection && !collapsed
          if (item.section) lastSection = item.section

          return (
            <div key={item.href}>
              {showSection && (
                <div className="px-3 pt-5 pb-1.5 text-[10px] uppercase tracking-widest text-slate-600 font-semibold">
                  {item.section}
                </div>
              )}
              <Link
                href={item.href}
                onClick={onMobileClose}
                title={collapsed ? item.label : undefined}
                className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                  collapsed ? 'justify-center' : ''
                } ${
                  isActive
                    ? 'bg-accent/10 text-accent font-medium'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
                }`}
                aria-current={isActive ? 'page' : undefined}
              >
                <item.icon size={18} aria-hidden="true" />
                {!collapsed && item.label}
              </Link>
            </div>
          )
        })}
      </nav>

      {/* Knowledge base freshness */}
      <div
        className={`mx-2 mb-2 px-3 py-2 rounded-lg bg-white/[0.02] border border-white/[0.04] ${
          collapsed ? 'flex justify-center' : ''
        }`}
        title={collapsed ? `Knowledge base: ${KNOWLEDGE_BASE_META.chunks_count.toLocaleString()} chunks · ${KNOWLEDGE_BASE_META.frameworks_count} framework · Aggiornata al ${new Date(KNOWLEDGE_BASE_META.updated_at).toLocaleDateString('it-IT', { day: 'numeric', month: 'short', year: 'numeric' })}` : undefined}
      >
        {collapsed ? (
          <Database size={14} className="text-slate-500" />
        ) : (
          <div className="space-y-1">
            <div className="flex items-center gap-1.5 text-[10px] text-slate-500">
              <Database size={12} className="shrink-0" />
              <span className="uppercase tracking-wider font-medium">Knowledge Base</span>
            </div>
            <div className="text-[10px] text-slate-400">
              Aggiornata al{' '}
              <span className="text-slate-300 font-medium">
                {new Date(KNOWLEDGE_BASE_META.updated_at).toLocaleDateString('it-IT', { day: 'numeric', month: 'short', year: 'numeric' })}
              </span>
            </div>
            <div className="text-[9px] text-slate-600">
              {KNOWLEDGE_BASE_META.chunks_count.toLocaleString()} chunks · {KNOWLEDGE_BASE_META.frameworks_count} framework EU
            </div>
          </div>
        )}
      </div>

      {/* Collapse toggle (desktop) */}
      <button
        onClick={onToggle}
        className="hidden md:flex mx-2 mb-2 items-center justify-center py-1.5 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-white/[0.04] transition-colors"
        aria-label={collapsed ? 'Espandi sidebar' : 'Comprimi sidebar'}
      >
        {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
      </button>

      {/* User info + logout */}
      <div className={`px-3 py-4 border-t border-white/[0.06] ${collapsed ? 'flex justify-center' : ''}`}>
        {collapsed ? (
          <button onClick={logout} className="text-slate-500 hover:text-red-400 transition" title="Sign out" aria-label="Esci">
            <LogOut size={16} />
          </button>
        ) : (
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-accent/20 flex items-center justify-center text-accent text-xs font-bold flex-shrink-0" aria-hidden="true">
              {user?.name?.charAt(0).toUpperCase() || '?'}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium truncate">{user?.name || 'User'}</div>
              <div className="text-[11px] text-slate-500 truncate">{user?.organization_name}</div>
            </div>
            <button onClick={logout} className="text-slate-500 hover:text-red-400 transition" title="Sign out" aria-label="Esci">
              <LogOut size={16} />
            </button>
          </div>
        )}
      </div>
    </aside>
  )

  return (
    <>
      {/* Desktop sidebar */}
      <div className="hidden md:block fixed left-0 top-0 z-30">
        {sidebarContent}
      </div>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div className="md:hidden fixed inset-0 z-40">
          <div className="absolute inset-0 bg-black/60" onClick={onMobileClose} aria-hidden="true" />
          <div className="absolute left-0 top-0 h-full z-50">
            <button
              onClick={onMobileClose}
              className="absolute top-4 right-[-40px] w-8 h-8 flex items-center justify-center rounded-full bg-surface text-slate-400 hover:text-white"
              aria-label="Chiudi menu"
            >
              <X size={18} />
            </button>
            {sidebarContent}
          </div>
        </div>
      )}
    </>
  )
}
