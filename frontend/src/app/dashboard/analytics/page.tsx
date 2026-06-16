'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import type { SystemStats } from '@/lib/types'
import { FRAMEWORKS } from '@/lib/types'
import { BarChart3, TrendingUp, Activity } from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar,
  PieChart, Pie, Cell,
} from 'recharts'

const CHART_COLORS = ['#5b8cff', '#34d399', '#f59e0b', '#ef4f63', '#3b82f6', '#a855f7', '#14b8a6']

export default function AnalyticsPage() {
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
        Failed to load stats: {error}
      </div>
    )
  }

  if (!stats) {
    return (
      <div className="grid grid-cols-2 gap-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-64 bg-surface border border-white/[0.06] rounded-xl animate-pulse" />
        ))}
      </div>
    )
  }

  // Endpoint latency chart data
  const endpointData = Object.entries(stats.metrics.endpoints).map(([ep, m]) => ({
    name: ep.replace('POST ', '').replace('GET ', '').split('/').pop() || ep,
    requests: m.count,
    avgLatency: m.avg_latency_ms,
    maxLatency: m.max_latency_ms,
  }))

  // Framework radar chart — uses real gap analysis scores from session when available
  const gapScores: Record<string, number> = (() => {
    try {
      const stored = sessionStorage.getItem('normaai_gap_scores')
      return stored ? JSON.parse(stored) : {}
    } catch { return {} }
  })()

  const frameworkRadarData = FRAMEWORKS.map((fw, idx) => ({
    framework: fw.value,
    coverage: gapScores[fw.value] ?? null,
    placeholder: [72, 85, 58, 91, 66, 78, 63][idx] ?? 70,
  }))

  // Error rate pie
  const errorRate = stats.metrics.total_requests > 0
    ? (stats.metrics.error_count / stats.metrics.total_requests * 100)
    : 0
  const pieData = [
    { name: 'Success', value: stats.metrics.total_requests - stats.metrics.error_count },
    { name: 'Errors', value: stats.metrics.error_count },
  ]

  return (
    <div className="space-y-6">
      {/* Summary row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <MetricCard
          icon={Activity}
          label="Total Requests"
          value={stats.metrics.total_requests.toLocaleString()}
        />
        <MetricCard
          icon={TrendingUp}
          label="Error Rate"
          value={`${errorRate.toFixed(1)}%`}
          valueColor={errorRate > 5 ? 'text-red-400' : 'text-green-400'}
        />
        <MetricCard
          icon={BarChart3}
          label="Active Endpoints"
          value={Object.keys(stats.metrics.endpoints).length.toString()}
        />
      </div>

      {/* Charts grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Endpoint latency bar chart */}
        <div className="bg-surface border border-white/[0.06] rounded-xl p-5">
          <h3 className="text-xs uppercase tracking-widest text-slate-500 font-semibold mb-4">Endpoint Latency (ms)</h3>
          <div role="img" aria-label="Grafico a barre della latenza media e massima per endpoint API">
          {endpointData.length > 0 ? (
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={endpointData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#161c26" />
                <XAxis dataKey="name" tick={{ fill: '#6f7a8a', fontSize: 11 }} />
                <YAxis tick={{ fill: '#6f7a8a', fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ background: '#0d1117', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 8 }}
                  labelStyle={{ color: '#e2e8f0' }}
                />
                <Bar dataKey="avgLatency" name="Avg Latency" fill="#5b8cff" radius={[4, 4, 0, 0]} />
                <Bar dataKey="maxLatency" name="Max Latency" fill="#3a6cff" radius={[4, 4, 0, 0]} opacity={0.5} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[250px] flex items-center justify-center text-slate-500 text-sm">
              No endpoint data yet. Make some API calls to see metrics.
            </div>
          )}
          </div>
        </div>

        {/* Success/Error pie */}
        <div className="bg-surface border border-white/[0.06] rounded-xl p-5">
          <h3 className="text-xs uppercase tracking-widest text-slate-500 font-semibold mb-4">Request Status</h3>
          <div role="img" aria-label="Grafico a torta della percentuale di richieste riuscite ed errori">
          {stats.metrics.total_requests > 0 ? (
            <ResponsiveContainer width="100%" height={250}>
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={90}
                  dataKey="value"
                  label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                >
                  <Cell fill="#34d399" />
                  <Cell fill="#ef4f63" />
                </Pie>
                <Tooltip
                  contentStyle={{ background: '#0d1117', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 8 }}
                />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[250px] flex items-center justify-center text-slate-500 text-sm">
              No requests recorded yet.
            </div>
          )}
          </div>
        </div>

        {/* Framework radar */}
        <div className="bg-surface border border-white/[0.06] rounded-xl p-5">
          <h3 className="text-xs uppercase tracking-widest text-slate-500 font-semibold mb-4">Framework Coverage</h3>
          <div role="img" aria-label="Grafico radar dei punteggi di compliance per framework">
          <ResponsiveContainer width="100%" height={250}>
            <RadarChart data={frameworkRadarData.map(d => ({ ...d, value: d.coverage ?? d.placeholder }))}>
              <PolarGrid stroke="#161c26" />
              <PolarAngleAxis dataKey="framework" tick={{ fill: '#aab3c0', fontSize: 11 }} />
              <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fill: '#6f7a8a', fontSize: 10 }} />
              <Radar name="Coverage" dataKey="value" stroke="#5b8cff" fill="#5b8cff" fillOpacity={0.2} />
            </RadarChart>
          </ResponsiveContainer>
          </div>
          <p className={`text-[10px] text-center mt-1 ${frameworkRadarData.some(d => d.coverage !== null) ? 'text-green-400/70' : 'text-yellow-500/80'}`}>
            {frameworkRadarData.every(d => d.coverage === null)
              ? 'Sample data — run Gap Analysis to see real coverage scores'
              : `Real scores for ${frameworkRadarData.filter(d => d.coverage !== null).map(d => d.framework).join(', ')} · sample for remaining`}
          </p>
        </div>

        {/* Request volume by endpoint */}
        <div className="bg-surface border border-white/[0.06] rounded-xl p-5">
          <h3 className="text-xs uppercase tracking-widest text-slate-500 font-semibold mb-4">Request Volume</h3>
          <div role="img" aria-label="Grafico a barre orizzontali del volume di richieste per endpoint">
          {endpointData.length > 0 ? (
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={endpointData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#161c26" />
                <XAxis type="number" tick={{ fill: '#6f7a8a', fontSize: 11 }} />
                <YAxis type="category" dataKey="name" tick={{ fill: '#6f7a8a', fontSize: 11 }} width={80} />
                <Tooltip
                  contentStyle={{ background: '#0d1117', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 8 }}
                />
                <Bar dataKey="requests" name="Requests" fill="#34d399" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[250px] flex items-center justify-center text-slate-500 text-sm">
              No requests recorded yet.
            </div>
          )}
          </div>
        </div>
      </div>
    </div>
  )
}

function MetricCard({ icon: Icon, label, value, valueColor }: {
  icon: React.ElementType; label: string; value: string; valueColor?: string
}) {
  return (
    <div className="bg-surface border border-white/[0.06] rounded-xl p-5">
      <div className="flex items-center gap-2 mb-2">
        <Icon size={16} className="text-accent" />
        <span className="text-xs text-slate-500 uppercase tracking-wider">{label}</span>
      </div>
      <div className={`text-2xl font-bold ${valueColor || 'text-white'}`}>{value}</div>
    </div>
  )
}
