'use client'

import { useState, useMemo } from 'react'
import { DEMO_AUDIT_EVENTS } from '@/lib/mock-data'
import type { AuditEvent } from '@/lib/types'
import { Shield, Download, Search, Filter, Clock } from 'lucide-react'

const ACTION_CONFIG: Record<string, { label: string; color: string }> = {
  'qa.query': { label: 'Q&A', color: 'text-blue-400 bg-blue-400/10 border-blue-400/20' },
  'gap_analysis.run': { label: 'Gap Analysis', color: 'text-purple-400 bg-purple-400/10 border-purple-400/20' },
  'monitor.analyze': { label: 'Monitor', color: 'text-yellow-400 bg-yellow-400/10 border-yellow-400/20' },
  'report.generate': { label: 'Report', color: 'text-green-400 bg-green-400/10 border-green-400/20' },
  'report.export': { label: 'Export', color: 'text-green-400 bg-green-400/10 border-green-400/20' },
  'alert.dismiss': { label: 'Alert', color: 'text-orange-400 bg-orange-400/10 border-orange-400/20' },
  'client.create': { label: 'Client', color: 'text-cyan-400 bg-cyan-400/10 border-cyan-400/20' },
  'client.update': { label: 'Client', color: 'text-cyan-400 bg-cyan-400/10 border-cyan-400/20' },
  'document.upload': { label: 'Document', color: 'text-teal-400 bg-teal-400/10 border-teal-400/20' },
  'auth.login': { label: 'Auth', color: 'text-slate-400 bg-slate-400/10 border-slate-400/20' },
  'system.config_change': { label: 'System', color: 'text-red-400 bg-red-400/10 border-red-400/20' },
}

const RESOURCE_TYPES = ['all', 'qa', 'gap_analysis', 'monitor', 'report', 'alert', 'client', 'document', 'auth', 'system'] as const
const DATE_RANGES = [
  { label: 'Oggi', value: 'today' },
  { label: '7 giorni', value: '7d' },
  { label: '30 giorni', value: '30d' },
  { label: 'Tutto', value: 'all' },
] as const

export default function AuditTrailPage() {
  const [resourceFilter, setResourceFilter] = useState<string>('all')
  const [dateRange, setDateRange] = useState<string>('all')
  const [searchText, setSearchText] = useState('')
  const [frameworkFilter, setFrameworkFilter] = useState<string>('all')

  const filtered = useMemo(() => {
    let events = [...DEMO_AUDIT_EVENTS]

    if (resourceFilter !== 'all') {
      events = events.filter(e => e.resource_type === resourceFilter)
    }

    if (frameworkFilter !== 'all') {
      events = events.filter(e => e.framework === frameworkFilter)
    }

    if (searchText.trim()) {
      const q = searchText.toLowerCase()
      events = events.filter(e =>
        e.details.toLowerCase().includes(q) ||
        e.user_name.toLowerCase().includes(q) ||
        e.action.toLowerCase().includes(q)
      )
    }

    if (dateRange !== 'all') {
      const now = new Date()
      const cutoff = new Date()
      if (dateRange === 'today') cutoff.setHours(0, 0, 0, 0)
      else if (dateRange === '7d') cutoff.setDate(now.getDate() - 7)
      else if (dateRange === '30d') cutoff.setDate(now.getDate() - 30)
      events = events.filter(e => new Date(e.timestamp) >= cutoff)
    }

    return events
  }, [resourceFilter, dateRange, searchText, frameworkFilter])

  const handleExportCSV = () => {
    const header = 'Timestamp,User,Email,Action,Resource,Details,Framework,IP'
    const rows = filtered.map(e =>
      `"${e.timestamp}","${e.user_name}","${e.user_email}","${e.action}","${e.resource_type}","${e.details.replace(/"/g, '""')}","${e.framework || ''}","${e.ip_address}"`
    )
    const csv = [header, ...rows].join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `normaai-audit-trail-${new Date().toISOString().split('T')[0]}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-6 max-w-6xl">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Shield size={20} className="text-accent" /> Audit Trail
          </h2>
          <p className="text-sm text-slate-500">
            Registro completo delle attivit&agrave; &mdash; retention 7+ anni (Basel III / MiFID II)
          </p>
        </div>
        <button
          onClick={handleExportCSV}
          className="px-4 py-2 text-sm bg-surface border border-white/[0.06] rounded-lg text-slate-300 hover:text-white hover:border-accent/30 transition flex items-center gap-2"
        >
          <Download size={14} /> Esporta CSV
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            placeholder="Cerca per utente, azione, dettagli..."
            aria-label="Cerca eventi audit"
            className="w-full pl-9 pr-3 py-2 bg-surface border border-white/[0.06] rounded-lg text-sm text-white placeholder-slate-500 focus:outline-none focus:border-accent/40 transition"
          />
        </div>

        <select
          value={resourceFilter}
          onChange={(e) => setResourceFilter(e.target.value)}
          aria-label="Filtra per risorsa"
          className="px-3 py-2 bg-surface border border-white/[0.06] rounded-lg text-sm text-slate-300 focus:outline-none"
        >
          <option value="all">Tutte le risorse</option>
          {RESOURCE_TYPES.filter(r => r !== 'all').map(r => (
            <option key={r} value={r}>{r.replace('_', ' ').toUpperCase()}</option>
          ))}
        </select>

        <select
          value={frameworkFilter}
          onChange={(e) => setFrameworkFilter(e.target.value)}
          aria-label="Filtra per framework"
          className="px-3 py-2 bg-surface border border-white/[0.06] rounded-lg text-sm text-slate-300 focus:outline-none"
        >
          <option value="all">Tutti i framework</option>
          {['CSRD', 'DORA', 'NIS2', 'GDPR', 'AI_ACT', 'CSDDD', 'TAXONOMY'].map(fw => (
            <option key={fw} value={fw}>{fw}</option>
          ))}
        </select>

        <div className="flex bg-surface border border-white/[0.06] rounded-lg overflow-hidden">
          {DATE_RANGES.map(dr => (
            <button
              key={dr.value}
              onClick={() => setDateRange(dr.value)}
              className={`px-3 py-2 text-xs font-medium transition ${
                dateRange === dr.value
                  ? 'bg-accent/10 text-accent'
                  : 'text-slate-400 hover:text-white hover:bg-white/[0.04]'
              }`}
            >
              {dr.label}
            </button>
          ))}
        </div>
      </div>

      {/* Results count */}
      <div className="text-xs text-slate-500">
        {filtered.length} eventi {filtered.length !== DEMO_AUDIT_EVENTS.length && `(filtrati da ${DEMO_AUDIT_EVENTS.length})`}
      </div>

      {/* Table */}
      <div className="bg-surface border border-white/[0.06] rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-500 text-left text-xs border-b border-white/[0.04]">
                <th className="px-4 py-3 font-medium"><Clock size={12} className="inline mr-1" />Timestamp</th>
                <th className="px-4 py-3 font-medium">Utente</th>
                <th className="px-4 py-3 font-medium">Azione</th>
                <th className="px-4 py-3 font-medium">Dettagli</th>
                <th className="px-4 py-3 font-medium">Framework</th>
                <th className="px-4 py-3 font-medium">IP</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.04]">
              {filtered.map(event => {
                const actionCfg = ACTION_CONFIG[event.action] || { label: event.action, color: 'text-slate-400 bg-slate-400/10 border-slate-400/20' }
                return (
                  <tr key={event.id} className="hover:bg-white/[0.02] transition">
                    <td className="px-4 py-3 text-xs text-slate-400 whitespace-nowrap font-mono">
                      {new Date(event.timestamp).toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit' })}{' '}
                      {new Date(event.timestamp).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' })}
                    </td>
                    <td className="px-4 py-3">
                      <div className="text-xs font-medium text-slate-300">{event.user_name}</div>
                      <div className="text-[10px] text-slate-600">{event.user_email}</div>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`text-[10px] px-2 py-0.5 rounded border font-medium ${actionCfg.color}`}>
                        {actionCfg.label}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-300 max-w-xs truncate">{event.details}</td>
                    <td className="px-4 py-3">
                      {event.framework && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent/10 text-accent font-medium">
                          {event.framework}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-600 font-mono">{event.ip_address}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {filtered.length === 0 && (
          <div className="py-12 text-center text-slate-500 text-sm">
            <Filter size={24} className="mx-auto mb-2 text-slate-600" />
            Nessun evento corrisponde ai filtri selezionati
          </div>
        )}
      </div>

      {/* Compliance note */}
      <p className="text-[9px] text-slate-600 italic">
        Gli audit log sono conservati per un minimo di 7 anni in conformit&agrave; ai requisiti Basel III e MiFID II.
        Per export certificati contattare l&apos;amministratore di sistema.
      </p>
    </div>
  )
}
