'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import type { SystemStats } from '@/lib/types'
import { Activity, Database, Brain, Shield, Zap, Server } from 'lucide-react'

export default function DashboardOverview() {
  const [stats, setStats] = useState<SystemStats | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.get<SystemStats>('/api/v1/stats')
      .then(setStats)
      .catch((e) => setError(e.message))
  }, [])

  if (error) {
    return (
      <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400">
        Failed to load system stats: {error}
      </div>
    )
  }

  if (!stats) {
    return (
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-28 bg-surface border border-white/[0.06] rounded-xl animate-pulse" />
        ))}
      </div>
    )
  }

  const isHealthy = stats.qdrant_available && stats.llm_available

  return (
    <div className="space-y-6">
      {/* Status banner */}
      <div className={`flex items-center gap-3 px-4 py-3 rounded-lg border ${
        isHealthy
          ? 'bg-green-500/5 border-green-500/20 text-green-400'
          : 'bg-yellow-500/5 border-yellow-500/20 text-yellow-400'
      }`}>
        <div className={`w-2.5 h-2.5 rounded-full ${isHealthy ? 'bg-green-400' : 'bg-yellow-400'}`} />
        <span className="text-sm font-medium">
          {isHealthy ? 'All systems operational' : 'Partial — some services unavailable'}
        </span>
        <span className="text-xs text-slate-500 ml-auto">v{stats.version} &middot; {stats.environment}</span>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={Database}
          label="Chunks Indexed"
          value={stats.qdrant?.points_count?.toLocaleString() || '—'}
          color="text-blue-400"
        />
        <StatCard
          icon={Shield}
          label="EU Frameworks"
          value="7"
          color="text-green-400"
        />
        <StatCard
          icon={Activity}
          label="Total Requests"
          value={stats.metrics.total_requests.toLocaleString()}
          color="text-accent"
        />
        <StatCard
          icon={Zap}
          label="Errors"
          value={stats.metrics.error_count.toLocaleString()}
          color={stats.metrics.error_count > 0 ? 'text-red-400' : 'text-green-400'}
        />
      </div>

      {/* Service status */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-surface border border-white/[0.06] rounded-xl p-5">
          <h3 className="text-xs uppercase tracking-widest text-slate-500 font-semibold mb-4">Services</h3>
          <div className="space-y-3">
            <ServiceRow label="Qdrant Vector DB" status={stats.qdrant_available} />
            <ServiceRow label={`LLM (${stats.llm_provider?.toUpperCase()})`} status={stats.llm_available} detail={stats.llm_model} />
            <ServiceRow label="PostgreSQL" status={true} />
            <ServiceRow label="Redis Cache" status={true} />
          </div>
        </div>

        <div className="bg-surface border border-white/[0.06] rounded-xl p-5">
          <h3 className="text-xs uppercase tracking-widest text-slate-500 font-semibold mb-4">Frameworks Monitored</h3>
          <div className="grid grid-cols-2 gap-2">
            {['CSRD', 'CSDDD', 'AI Act', 'DORA', 'NIS2', 'Taxonomy', 'GDPR'].map((fw) => (
              <div key={fw} className="flex items-center gap-2 px-3 py-2 bg-surface2 rounded-lg">
                <div className="w-1.5 h-1.5 rounded-full bg-green-400" />
                <span className="text-sm font-medium">{fw}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Endpoint metrics */}
      {Object.keys(stats.metrics.endpoints).length > 0 && (
        <div className="bg-surface border border-white/[0.06] rounded-xl p-5">
          <h3 className="text-xs uppercase tracking-widest text-slate-500 font-semibold mb-4">Endpoint Performance</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-slate-500 text-left">
                  <th className="pb-3 font-medium">Endpoint</th>
                  <th className="pb-3 font-medium text-right">Requests</th>
                  <th className="pb-3 font-medium text-right">Avg Latency</th>
                  <th className="pb-3 font-medium text-right">Max Latency</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.04]">
                {Object.entries(stats.metrics.endpoints).map(([ep, m]) => (
                  <tr key={ep}>
                    <td className="py-2.5 font-mono text-xs text-slate-300">{ep}</td>
                    <td className="py-2.5 text-right">{m.count}</td>
                    <td className="py-2.5 text-right text-slate-400">{m.avg_latency_ms}ms</td>
                    <td className="py-2.5 text-right text-slate-400">{m.max_latency_ms}ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

function StatCard({ icon: Icon, label, value, color }: { icon: React.ElementType; label: string; value: string; color: string }) {
  return (
    <div className="bg-surface border border-white/[0.06] rounded-xl p-5">
      <div className="flex items-center gap-3 mb-3">
        <Icon size={18} className={color} />
        <span className="text-xs text-slate-500 uppercase tracking-wider">{label}</span>
      </div>
      <div className="text-2xl font-bold">{value}</div>
    </div>
  )
}

function ServiceRow({ label, status, detail }: { label: string; status: boolean; detail?: string }) {
  return (
    <div className="flex items-center gap-3">
      <div className={`w-2 h-2 rounded-full shrink-0 ${status ? 'bg-green-400' : 'bg-red-400'}`} />
      <span className="text-sm">{label}</span>
      <div className="ml-auto flex items-center gap-3">
        {detail && <span className="text-xs text-slate-500 hidden sm:inline">{detail}</span>}
        <span className={`text-xs shrink-0 ${status ? 'text-green-400' : 'text-red-400'}`}>
          {status ? 'Online' : 'Offline'}
        </span>
      </div>
    </div>
  )
}
