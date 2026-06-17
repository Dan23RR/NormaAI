'use client'

import { useParams, useRouter } from 'next/navigation'
import { useState, useEffect } from 'react'
import { api } from '@/lib/api'
import { DEMO_CLIENT_COMPLIANCE } from '@/lib/mock-data'
import { FRAMEWORKS } from '@/lib/types'
import { ArrowLeft, TrendingUp, TrendingDown, Minus, FileCheck, Building2 } from 'lucide-react'

export default function ClientDetailPage() {
  const params = useParams()
  const router = useRouter()
  const clientId = params.id as string
  const [clientName, setClientName] = useState('')

  useEffect(() => {
    // In demo mode, look up client name from the API/mock
    const loadClient = async () => {
      try {
        const res = await api.get<{ data: { id: string; name: string }[] } | { id: string; name: string }[]>('/api/v1/clients')
        const clients = Array.isArray(res) ? res : res.data ?? []
        const found = clients.find((c: { id: string }) => c.id === clientId)
        if (found) setClientName(found.name)
      } catch {
        // fallback
      }
    }
    loadClient()
  }, [clientId])

  const compliance = DEMO_CLIENT_COMPLIANCE[clientName]

  return (
    <div className="space-y-6 max-w-5xl">
      {/* Back + Header */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => router.push('/dashboard/clients')}
          className="p-2 rounded-lg hover:bg-white/[0.04] text-slate-400 hover:text-white transition"
        >
          <ArrowLeft size={18} />
        </button>
        <div>
          <div className="flex items-center gap-2">
            <Building2 size={18} className="text-accent" />
            <h2 className="text-lg font-semibold">{clientName || 'Loading...'}</h2>
          </div>
          <p className="text-xs text-slate-500">Compliance Dashboard - Monitoraggio continuo</p>
        </div>
      </div>

      {!compliance ? (
        <div className="py-16 text-center text-slate-500">
          <Building2 size={40} className="mx-auto mb-3 text-slate-600" />
          <p className="text-sm">
            {clientName ? 'Nessun dato di compliance disponibile per questo client.' : 'Caricamento...'}
          </p>
          <p className="text-xs text-slate-600 mt-1">
            Esegui una Gap Analysis per questo client per iniziare il monitoraggio.
          </p>
        </div>
      ) : (
        <>
          {/* Score cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {compliance.scores.map(s => {
              const fwDef = FRAMEWORKS.find(f => f.value === s.framework)
              const delta = s.score - s.previous_score
              return (
                <div key={s.framework} className="bg-surface border border-white/[0.06] rounded-xl p-4">
                  <div className="flex items-center justify-between mb-2">
                    <span
                      className="text-[10px] px-1.5 py-0.5 rounded font-semibold"
                      style={{ color: fwDef?.color, backgroundColor: `${fwDef?.color}15` }}
                    >
                      {s.framework}
                    </span>
                    <div className={`flex items-center gap-0.5 text-[10px] ${
                      s.trend === 'up' ? 'text-blue-400' : s.trend === 'down' ? 'text-orange-400' : 'text-slate-500'
                    }`}>
                      {s.trend === 'up' ? <TrendingUp size={10} /> : s.trend === 'down' ? <TrendingDown size={10} /> : <Minus size={10} />}
                      {delta > 0 ? '+' : ''}{delta}%
                    </div>
                  </div>
                  <div className="text-2xl font-bold">{s.score}%</div>
                  <div className="w-full h-1.5 bg-white/[0.04] rounded-full mt-2 overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{
                        width: `${s.score}%`,
                        backgroundColor: s.score >= 80 ? '#3b82f6' : s.score >= 60 ? '#f59e0b' : '#f97316',
                      }}
                    />
                  </div>
                  <div className="text-[9px] text-slate-600 mt-1">
                    Ultimo: {new Date(s.last_assessed).toLocaleDateString('it-IT')}
                  </div>
                </div>
              )
            })}
          </div>

          {/* Compliance history chart (CSS bars) */}
          <div className="bg-surface border border-white/[0.06] rounded-xl p-5">
            <h3 className="text-xs uppercase tracking-widest text-slate-500 font-semibold mb-4">
              Trend Compliance (ultimi 6 mesi)
            </h3>
            <div className="flex gap-1 items-end h-40">
              {compliance.history.map((h, i) => {
                const frameworks = Object.keys(h.scores)
                const avg = Math.round(
                  Object.values(h.scores).reduce((a, b) => a + b, 0) / frameworks.length
                )
                return (
                  <div key={i} className="flex-1 flex flex-col items-center gap-1">
                    <span className="text-[10px] text-slate-400 font-medium">{avg}%</span>
                    <div className="w-full flex gap-0.5 items-end" style={{ height: '120px' }}>
                      {frameworks.map(fw => {
                        const fwDef = FRAMEWORKS.find(f => f.value === fw)
                        return (
                          <div
                            key={fw}
                            className="flex-1 rounded-t transition-all duration-300"
                            style={{
                              height: `${h.scores[fw]}%`,
                              backgroundColor: fwDef?.color || '#6366f1',
                              opacity: 0.7,
                            }}
                            title={`${fw}: ${h.scores[fw]}%`}
                          />
                        )
                      })}
                    </div>
                    <span className="text-[9px] text-slate-600">{h.month}</span>
                  </div>
                )
              })}
            </div>
            {/* Legend */}
            <div className="flex flex-wrap gap-3 mt-3 pt-3 border-t border-white/[0.04]">
              {compliance.scores.map(s => {
                const fwDef = FRAMEWORKS.find(f => f.value === s.framework)
                return (
                  <div key={s.framework} className="flex items-center gap-1.5 text-[10px] text-slate-400">
                    <div className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: fwDef?.color, opacity: 0.7 }} />
                    {s.framework}
                  </div>
                )
              })}
            </div>
          </div>

          {/* Audit Pack button */}
          <div className="bg-surface border border-white/[0.06] rounded-xl p-5 flex items-center justify-between">
            <div>
              <h3 className="text-sm font-medium flex items-center gap-2">
                <FileCheck size={16} className="text-accent" />
                Audit Pack Generator
              </h3>
              <p className="text-xs text-slate-500 mt-1">
                Genera il pacchetto evidenze completo per auditor e regolatori
              </p>
            </div>
            <button
              onClick={() => alert('Audit Pack generation: Gap Analysis + Remediation Actions + Approval Chain + Audit Trail.\nFunzionalità in sviluppo.')}
              className="px-4 py-2 rounded-lg bg-gradient-to-r from-accent to-accent2 text-white text-sm font-medium hover:opacity-90 transition flex items-center gap-2"
            >
              <FileCheck size={14} />
              Genera Audit Pack
            </button>
          </div>
          {/* AI disclosure */}
          <p className="text-[9px] text-slate-600 italic mt-2">
            I punteggi di compliance sono stime qualitative generate da AI (AI Act Art. 50, Reg. UE 2024/1689) - non costituiscono certificazione. Verificare con auditor qualificati.
          </p>
        </>
      )}
    </div>
  )
}
