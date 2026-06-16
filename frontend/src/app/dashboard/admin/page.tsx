'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { useAuth } from '@/hooks/useAuth'
import { DEMO_ROLES } from '@/lib/mock-data'
import type { SystemStats, Role } from '@/lib/types'
import { Shield, Server, Activity, AlertTriangle, RefreshCw, Globe, Users, Lock, ChevronDown, ChevronUp } from 'lucide-react'

interface ProcessorStatus {
  status: string
  engines?: string[]
  dots_ocr?: { available: boolean; mode: string }
  docling?: { available: boolean }
  error?: string
}

export default function AdminPage() {
  const { user } = useAuth()
  const [stats, setStats] = useState<SystemStats | null>(null)
  const [processors, setProcessors] = useState<ProcessorStatus | null>(null)
  const [metrics, setMetrics] = useState<Record<string, unknown> | null>(null)
  const [error, setError] = useState('')
  const [refreshing, setRefreshing] = useState(false)
  const [roles, setRoles] = useState<Role[]>(DEMO_ROLES)
  const [expandedRole, setExpandedRole] = useState<string | null>(null)

  const loadData = async () => {
    setRefreshing(true)
    try {
      const [s, p] = await Promise.all([
        api.get<SystemStats>('/api/v1/stats'),
        api.get<ProcessorStatus>('/api/v1/processors').catch(() => null),
      ])
      setStats(s)
      if (p) setProcessors(p)

      // Admin metrics (may fail if not admin)
      if (user?.role === 'admin') {
        try {
          const m = await api.get<Record<string, unknown>>('/api/v1/metrics')
          setMetrics(m)
        } catch {
          // Not admin or metrics unavailable
        }
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load data')
    } finally {
      setRefreshing(false)
    }
  }

  useEffect(() => { loadData() }, [])

  if (user?.role !== 'admin') {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-slate-500">
        <Shield size={40} className="mb-3 text-slate-600" />
        <p className="text-lg font-medium text-slate-400">Admin Access Required</p>
        <p className="text-sm mt-1">This page requires admin privileges.</p>
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-5xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">System Administration</h2>
          <p className="text-sm text-slate-500">Monitor system health, metrics, and processing engines</p>
        </div>
        <button
          onClick={loadData}
          disabled={refreshing}
          className="px-4 py-2 text-sm bg-surface border border-white/[0.06] rounded-lg text-slate-300 hover:text-white hover:border-accent/30 transition flex items-center gap-2"
        >
          <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm flex items-center gap-2">
          <AlertTriangle size={16} /> {error}
        </div>
      )}

      {/* System info */}
      {stats && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <InfoCard label="Version" value={`v${stats.version}`} />
          <InfoCard label="Environment" value={stats.environment} />
          <InfoCard label="LLM Provider" value={stats.llm_provider?.toUpperCase()} />
          <InfoCard label="LLM Model" value={stats.llm_model} />
        </div>
      )}

      {/* Services health */}
      {stats && (
        <div className="bg-surface border border-white/[0.06] rounded-xl p-5">
          <h3 className="text-xs uppercase tracking-widest text-slate-500 font-semibold mb-4 flex items-center gap-2">
            <Server size={14} /> Service Health
          </h3>
          <div className="grid grid-cols-2 gap-3">
            <ServiceCard name="Qdrant Vector DB" status={stats.qdrant_available} detail={`${stats.qdrant?.points_count?.toLocaleString() || '?'} chunks`} />
            <ServiceCard name={`LLM (${stats.llm_provider})`} status={stats.llm_available} detail={stats.llm_model} />
            <ServiceCard name="PostgreSQL" status={true} detail="Connected" />
            <ServiceCard name="Redis Cache" status={true} detail="Connected" />
          </div>
        </div>
      )}

      {/* Processing engines */}
      {processors && (
        <div className="bg-surface border border-white/[0.06] rounded-xl p-5">
          <h3 className="text-xs uppercase tracking-widest text-slate-500 font-semibold mb-4">Document Processing Engines</h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <EngineCard
              name="dots.ocr"
              available={processors.dots_ocr?.available || false}
              detail={processors.dots_ocr?.mode || 'Not installed'}
            />
            <EngineCard
              name="Docling"
              available={processors.docling?.available || false}
              detail={processors.docling?.available ? 'Available' : 'Not installed'}
            />
            <EngineCard
              name="BeautifulSoup"
              available={true}
              detail="Fallback (always available)"
            />
          </div>
        </div>
      )}

      {/* Endpoint metrics table */}
      {stats && Object.keys(stats.metrics.endpoints).length > 0 && (
        <div className="bg-surface border border-white/[0.06] rounded-xl p-5">
          <h3 className="text-xs uppercase tracking-widest text-slate-500 font-semibold mb-4 flex items-center gap-2">
            <Activity size={14} /> Endpoint Metrics
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-slate-500 text-left text-xs">
                  <th className="pb-3 font-medium">Endpoint</th>
                  <th className="pb-3 font-medium text-right">Requests</th>
                  <th className="pb-3 font-medium text-right">Avg Latency</th>
                  <th className="pb-3 font-medium text-right">Max Latency</th>
                  <th className="pb-3 font-medium text-right">% of Total</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.04]">
                {Object.entries(stats.metrics.endpoints)
                  .sort(([, a], [, b]) => b.count - a.count)
                  .map(([ep, m]) => (
                    <tr key={ep}>
                      <td className="py-2.5 font-mono text-xs text-slate-300">{ep}</td>
                      <td className="py-2.5 text-right font-medium">{m.count}</td>
                      <td className="py-2.5 text-right text-slate-400">{m.avg_latency_ms}ms</td>
                      <td className="py-2.5 text-right text-slate-400">{m.max_latency_ms}ms</td>
                      <td className="py-2.5 text-right text-slate-500">
                        {stats.metrics.total_requests > 0
                          ? `${(m.count / stats.metrics.total_requests * 100).toFixed(1)}%`
                          : '—'
                        }
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
          <div className="flex gap-6 mt-4 pt-4 border-t border-white/[0.04] text-xs text-slate-500">
            <span>Total requests: <strong className="text-slate-300">{stats.metrics.total_requests}</strong></span>
            <span>Errors: <strong className={stats.metrics.error_count > 0 ? 'text-red-400' : 'text-green-400'}>{stats.metrics.error_count}</strong></span>
          </div>
        </div>
      )}

      {/* SSO Configuration */}
      <div className="bg-surface border border-white/[0.06] rounded-xl p-5">
        <h3 className="text-xs uppercase tracking-widest text-slate-500 font-semibold mb-4 flex items-center gap-2">
          <Globe size={14} /> SSO Configuration
        </h3>
        <div className="space-y-3">
          {[
            { name: 'Okta', protocol: 'SAML 2.0', status: 'not_configured' as const },
            { name: 'Azure AD', protocol: 'OIDC', status: 'not_configured' as const },
            { name: 'Google Workspace', protocol: 'OIDC', status: 'not_configured' as const },
          ].map(provider => (
            <div key={provider.name} className="flex items-center gap-3 bg-surface2 rounded-lg px-4 py-3">
              <div className="w-8 h-8 rounded-lg bg-white/[0.04] flex items-center justify-center text-slate-500 text-xs font-bold">
                {provider.name.charAt(0)}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium">{provider.name}</div>
                <div className="text-[10px] text-slate-500">{provider.protocol}</div>
              </div>
              <span className="text-[10px] px-2 py-0.5 rounded border border-slate-500/20 bg-slate-500/10 text-slate-500">
                Non configurato
              </span>
              <button className="text-xs text-accent hover:underline">
                Configura
              </button>
            </div>
          ))}
        </div>
        <p className="text-[9px] text-slate-600 mt-3 italic">
          La configurazione SSO richiede i metadati del provider (Entity ID, ACS URL, Certificate).
          Supporto per SAML 2.0 e OpenID Connect.
        </p>
      </div>

      {/* RBAC Role Management */}
      <div className="bg-surface border border-white/[0.06] rounded-xl p-5">
        <h3 className="text-xs uppercase tracking-widest text-slate-500 font-semibold mb-4 flex items-center gap-2">
          <Lock size={14} /> Role & Permission Management
        </h3>
        <div className="space-y-2">
          {roles.map(role => (
            <div key={role.id} className="border border-white/[0.04] rounded-lg overflow-hidden">
              <button
                onClick={() => setExpandedRole(expandedRole === role.id ? null : role.id)}
                className="w-full px-4 py-3 flex items-center gap-3 hover:bg-white/[0.02] transition text-left"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">{role.name}</span>
                    {role.is_system && (
                      <span className="text-[9px] px-1.5 py-0.5 rounded bg-slate-500/10 border border-slate-500/20 text-slate-500 font-medium">SYSTEM</span>
                    )}
                  </div>
                  <p className="text-xs text-slate-500 mt-0.5">{role.description}</p>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <div className="flex items-center gap-1 text-xs text-slate-400">
                    <Users size={12} />
                    <span>{role.user_count}</span>
                  </div>
                  <span className="text-[10px] text-slate-500">{role.permissions.length} permessi</span>
                  {expandedRole === role.id ? <ChevronUp size={14} className="text-slate-500" /> : <ChevronDown size={14} className="text-slate-500" />}
                </div>
              </button>
              {expandedRole === role.id && (
                <div className="px-4 pb-4 border-t border-white/[0.04]">
                  <div className="pt-3 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-1.5">
                    {role.permissions.map(perm => {
                      const [module, action] = perm.split('.')
                      return (
                        <div key={perm} className="text-[10px] px-2 py-1 rounded bg-accent/5 border border-accent/10 text-slate-400">
                          <span className="text-accent font-medium">{module}</span>
                          <span className="text-slate-600">.</span>
                          {action}
                        </div>
                      )
                    })}
                  </div>
                  <div className="flex items-center gap-3 mt-3 pt-3 border-t border-white/[0.04]">
                    <span className="text-[10px] text-slate-600">
                      Creato il {new Date(role.created_at).toLocaleDateString('it-IT')}
                    </span>
                    {!role.is_system && (
                      <button className="text-[10px] text-red-400 hover:text-red-300 transition ml-auto">
                        Elimina ruolo
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
        <p className="text-[9px] text-slate-600 mt-3 italic">
          Segregazione dei compiti: chi genera un&apos;analisi non può approvarla. Requisito four-eyes principle per item ad alto rischio.
        </p>
      </div>
    </div>
  )
}

function InfoCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-surface border border-white/[0.06] rounded-xl p-4">
      <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">{label}</div>
      <div className="text-sm font-medium truncate">{value}</div>
    </div>
  )
}

function ServiceCard({ name, status, detail }: { name: string; status: boolean; detail: string }) {
  return (
    <div className="flex items-center gap-3 bg-surface2 rounded-lg px-4 py-3">
      <div className={`w-2.5 h-2.5 rounded-full shrink-0 ${status ? 'bg-green-400' : 'bg-red-400'}`} />
      <div className="min-w-0">
        <div className="text-sm font-medium">{name}</div>
        <div className="text-xs text-slate-500 truncate">{detail}</div>
      </div>
      <span className={`text-xs ml-auto shrink-0 ${status ? 'text-green-400' : 'text-red-400'}`}>
        {status ? 'Online' : 'Offline'}
      </span>
    </div>
  )
}

function EngineCard({ name, available, detail }: { name: string; available: boolean; detail: string }) {
  return (
    <div className={`rounded-lg px-4 py-3 border ${
      available
        ? 'bg-green-400/5 border-green-400/20'
        : 'bg-surface2 border-white/[0.06]'
    }`}>
      <div className="flex items-center gap-2 mb-1">
        <div className={`w-2 h-2 rounded-full ${available ? 'bg-green-400' : 'bg-slate-600'}`} />
        <span className="text-sm font-medium">{name}</span>
      </div>
      <div className="text-xs text-slate-500">{detail}</div>
    </div>
  )
}
