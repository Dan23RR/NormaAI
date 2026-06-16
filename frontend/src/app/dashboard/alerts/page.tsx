'use client'

import { useState, useEffect, useCallback } from 'react'
import { api } from '@/lib/api'
import { isDemoMode } from '@/lib/auth'
import type { Framework } from '@/lib/types'
import { FRAMEWORKS } from '@/lib/types'
import { DEMO_ALERTS, DEMO_ALERT_SUMMARY, mockDelay } from '@/lib/mock-data'
import { Bell, AlertTriangle, Shield, Eye, Filter, Loader2, X } from 'lucide-react'

type Severity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFORMATIONAL'

const SEVERITY_CONFIG: Record<Severity, { color: string; bg: string; border: string }> = {
  CRITICAL: { color: 'text-red-400', bg: 'bg-red-400/10', border: 'border-red-400/20' },
  HIGH: { color: 'text-orange-400', bg: 'bg-orange-400/10', border: 'border-orange-400/20' },
  MEDIUM: { color: 'text-yellow-400', bg: 'bg-yellow-400/10', border: 'border-yellow-400/20' },
  LOW: { color: 'text-blue-400', bg: 'bg-blue-400/10', border: 'border-blue-400/20' },
  INFORMATIONAL: { color: 'text-slate-400', bg: 'bg-slate-400/10', border: 'border-slate-400/20' },
}

const SEVERITIES: Severity[] = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFORMATIONAL']

interface Alert {
  id: string
  title: string
  description: string
  severity: Severity
  framework?: string
  is_read: boolean
  is_dismissed: boolean
  created_at: string
  source?: string
}

interface AlertSummary {
  total: number
  unread: number
  by_severity: Record<Severity, number>
}

const PREFS_KEY = 'normaai_alert_prefs'

interface AlertPrefs {
  severity: Severity | ''
  framework: Framework | ''
  readFilter: 'all' | 'read' | 'unread'
}

function loadPrefs(): AlertPrefs {
  if (typeof window === 'undefined') return { severity: '', framework: '', readFilter: 'all' }
  try {
    const raw = localStorage.getItem(PREFS_KEY)
    if (raw) return JSON.parse(raw)
  } catch { /* ignore */ }
  return { severity: '', framework: '', readFilter: 'all' }
}

function savePrefs(prefs: AlertPrefs) {
  try { localStorage.setItem(PREFS_KEY, JSON.stringify(prefs)) } catch { /* ignore */ }
}

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [summary, setSummary] = useState<AlertSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // Filters — always start clean (no persistence between sessions)
  const [severityFilter, setSeverityFilterRaw] = useState<Severity | ''>('')
  const [frameworkFilter, setFrameworkFilterRaw] = useState<Framework | ''>('')
  const [readFilter, setReadFilterRaw] = useState<'all' | 'read' | 'unread'>('all')
  const [showFilters, setShowFilters] = useState(false)

  // Wrappers that persist to localStorage
  const setSeverityFilter = useCallback((v: Severity | '') => {
    setSeverityFilterRaw(v)
    savePrefs({ severity: v, framework: frameworkFilter, readFilter })
  }, [frameworkFilter, readFilter])

  const setFrameworkFilter = useCallback((v: Framework | '') => {
    setFrameworkFilterRaw(v)
    savePrefs({ severity: severityFilter, framework: v, readFilter })
  }, [severityFilter, readFilter])

  const setReadFilter = useCallback((v: 'all' | 'read' | 'unread') => {
    setReadFilterRaw(v)
    savePrefs({ severity: severityFilter, framework: frameworkFilter, readFilter: v })
  }, [severityFilter, frameworkFilter])

  const fetchAlerts = useCallback(async () => {
    setLoading(true)
    setError('')

    try {
      if (isDemoMode()) {
        await mockDelay(400)
        let filtered = (DEMO_ALERTS as Alert[]).slice()
        if (severityFilter) filtered = filtered.filter(a => a.severity === severityFilter)
        if (frameworkFilter) filtered = filtered.filter(a => a.framework === frameworkFilter)
        if (readFilter === 'read') filtered = filtered.filter(a => a.is_read)
        if (readFilter === 'unread') filtered = filtered.filter(a => !a.is_read)
        setAlerts(filtered)
        setSummary(DEMO_ALERT_SUMMARY as AlertSummary)
        return
      }

      const params = new URLSearchParams()
      if (severityFilter) params.set('severity', severityFilter)
      if (frameworkFilter) params.set('framework', frameworkFilter)
      if (readFilter === 'read') params.set('is_read', 'true')
      if (readFilter === 'unread') params.set('is_read', 'false')
      params.set('limit', '20')
      params.set('offset', '0')

      const query = params.toString()
      const [alertsData, summaryData] = await Promise.all([
        api.get<Alert[]>(`/api/v1/alerts?${query}`),
        api.get<AlertSummary>('/api/v1/alerts/summary'),
      ])

      setAlerts(alertsData)
      setSummary(summaryData)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load alerts')
    } finally {
      setLoading(false)
    }
  }, [severityFilter, frameworkFilter, readFilter])

  useEffect(() => {
    fetchAlerts()
  }, [fetchAlerts])

  const patchAlert = useCallback(async (id: string, action: 'read' | 'dismiss', severity?: Severity, wasUnread?: boolean) => {
    try {
      if (!isDemoMode()) {
        await api.fetch(`/api/v1/alerts/${id}/${action}`, { method: 'PATCH' })
      } else {
        await mockDelay(200)
      }

      if (action === 'read') {
        setAlerts(prev => prev.map(a => a.id === id ? { ...a, is_read: true } : a))
        setSummary(prev => prev ? { ...prev, unread: Math.max(0, prev.unread - 1) } : prev)
      } else {
        setAlerts(prev => prev.filter(a => a.id !== id))
        setSummary(prev => {
          if (!prev) return prev
          const newBySeverity = { ...prev.by_severity }
          if (severity && newBySeverity[severity] > 0) newBySeverity[severity]--
          return {
            ...prev,
            total: Math.max(0, prev.total - 1),
            unread: Math.max(0, prev.unread - (wasUnread ? 1 : 0)),
            by_severity: newBySeverity,
          }
        })
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Action failed')
    }
  }, [])

  const activeFilterCount = [severityFilter, frameworkFilter, readFilter !== 'all' ? readFilter : ''].filter(Boolean).length

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Summary cards */}
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
          <div className="bg-surface border border-white/[0.06] rounded-xl p-4 col-span-2">
            <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">Total / Unread</div>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-bold text-white">{summary.total}</span>
              <span className="text-sm text-slate-400">/ {summary.unread} unread</span>
            </div>
          </div>
          {SEVERITIES.map(sev => {
            const cfg = SEVERITY_CONFIG[sev]
            const count = summary.by_severity[sev] || 0
            return (
              <div key={sev} className="bg-surface border border-white/[0.06] rounded-xl p-4">
                <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">{sev}</div>
                <div className={`text-xl font-bold ${cfg.color}`}>{count}</div>
              </div>
            )
          })}
        </div>
      )}

      {/* Filter bar */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => setShowFilters(!showFilters)}
          className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm border transition ${
            showFilters || activeFilterCount > 0
              ? 'border-accent/30 bg-accent/5 text-accent'
              : 'border-white/[0.06] bg-surface text-slate-400 hover:text-white'
          }`}
        >
          <Filter size={14} />
          Filters
          {activeFilterCount > 0 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-accent text-white font-medium">
              {activeFilterCount}
            </span>
          )}
        </button>

        {activeFilterCount > 0 && (
          <button
            onClick={() => { setSeverityFilter(''); setFrameworkFilter(''); setReadFilter('all'); savePrefs({ severity: '', framework: '', readFilter: 'all' }) }}
            className="text-xs text-slate-500 hover:text-white transition"
          >
            Clear all
          </button>
        )}
      </div>

      {showFilters && (
        <div className="flex flex-wrap gap-3 p-4 bg-surface border border-white/[0.06] rounded-xl">
          <div>
            <label className="block text-[10px] text-slate-500 mb-1 uppercase tracking-wider">Severity</label>
            <select
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value as Severity | '')}
              className="px-3 py-2 bg-surface2 border border-white/[0.06] rounded-lg text-sm text-white focus:outline-none focus:border-accent/40"
            >
              <option value="">All</option>
              {SEVERITIES.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-[10px] text-slate-500 mb-1 uppercase tracking-wider">Framework</label>
            <select
              value={frameworkFilter}
              onChange={(e) => setFrameworkFilter(e.target.value as Framework | '')}
              className="px-3 py-2 bg-surface2 border border-white/[0.06] rounded-lg text-sm text-white focus:outline-none focus:border-accent/40"
            >
              <option value="">All</option>
              {FRAMEWORKS.map(fw => <option key={fw.value} value={fw.value}>{fw.label}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-[10px] text-slate-500 mb-1 uppercase tracking-wider">Status</label>
            <select
              value={readFilter}
              onChange={(e) => setReadFilter(e.target.value as 'all' | 'read' | 'unread')}
              className="px-3 py-2 bg-surface2 border border-white/[0.06] rounded-lg text-sm text-white focus:outline-none focus:border-accent/40"
            >
              <option value="all">All</option>
              <option value="unread">Unread</option>
              <option value="read">Read</option>
            </select>
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm flex items-center gap-2">
          <AlertTriangle size={16} /> {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-16 text-slate-400">
          <Loader2 size={24} className="animate-spin mr-3" />
          <span>Loading alerts...</span>
        </div>
      )}

      {/* Alert list */}
      {!loading && alerts.length > 0 && (
        <div className="space-y-3">
          {alerts.map(alert => {
            const cfg = SEVERITY_CONFIG[alert.severity]
            return (
              <div
                key={alert.id}
                className={`bg-surface border rounded-xl p-5 transition ${
                  alert.is_read ? 'border-white/[0.06]' : 'border-white/[0.1]'
                }`}
              >
                <div className="flex items-start gap-3">
                  <Shield size={18} className={`${cfg.color} shrink-0 mt-0.5`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h4 className={`text-sm font-medium ${alert.is_read ? 'text-slate-300' : 'text-white'}`}>
                        {alert.title}
                      </h4>
                      <span className={`text-[10px] px-2 py-0.5 rounded border font-semibold ${cfg.bg} ${cfg.color} ${cfg.border}`}>
                        {alert.severity}
                      </span>
                      {alert.framework && (
                        <span className="text-[10px] px-1.5 py-0.5 bg-accent/10 text-accent rounded">
                          {alert.framework}
                        </span>
                      )}
                      {!alert.is_read && (
                        <span className="w-2 h-2 rounded-full bg-accent shrink-0" />
                      )}
                    </div>
                    <p className="text-sm text-slate-400 mt-1.5 leading-relaxed">{alert.description}</p>
                    <div className="flex items-center gap-3 mt-3">
                      <span className="text-[10px] text-slate-500">
                        {new Date(alert.created_at).toLocaleDateString('en-US', {
                          month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit',
                        })}
                      </span>
                      {alert.source && (
                        <span className="text-[10px] text-slate-500">Source: {alert.source}</span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    {!alert.is_read && (
                      <button
                        onClick={() => patchAlert(alert.id, 'read')}
                        title="Mark as read"
                        className="p-1.5 rounded-lg text-slate-500 hover:text-white hover:bg-surface2 transition"
                      >
                        <Eye size={14} />
                      </button>
                    )}
                    <button
                      onClick={() => patchAlert(alert.id, 'dismiss', alert.severity, !alert.is_read)}
                      title="Dismiss alert"
                      className="p-1.5 rounded-lg text-slate-500 hover:text-red-400 hover:bg-red-400/10 transition"
                    >
                      <X size={14} />
                    </button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Empty state */}
      {!loading && alerts.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 text-slate-500">
          <Bell size={40} className="mb-3 text-slate-600" />
          <p className="text-lg font-medium text-slate-400">No alerts</p>
          <p className="text-sm mt-1">
            {activeFilterCount > 0
              ? 'No alerts match your current filters'
              : 'You are all caught up — no regulatory alerts at this time'}
          </p>
          {activeFilterCount > 0 && (
            <button
              onClick={() => { setSeverityFilter(''); setFrameworkFilter(''); setReadFilter('all'); savePrefs({ severity: '', framework: '', readFilter: 'all' }) }}
              className="mt-4 px-4 py-2 text-sm rounded-lg border border-white/[0.06] bg-surface text-slate-400 hover:text-white transition"
            >
              Clear filters
            </button>
          )}
        </div>
      )}

      {/* AI disclosure */}
      <p className="text-[9px] text-slate-600 italic mt-4">
        Gli alert sono generati da AI (AI Act Art. 50, Reg. UE 2024/1689) — verificare con fonti ufficiali prima di decisioni vincolanti.
      </p>
    </div>
  )
}
