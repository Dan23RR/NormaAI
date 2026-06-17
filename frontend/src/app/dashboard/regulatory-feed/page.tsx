'use client'

import { useState } from 'react'
import { Rss, ExternalLink, Clock, AlertTriangle, Filter } from 'lucide-react'
import { FRAMEWORKS } from '@/lib/types'

interface RegUpdate {
  id: string
  title: string
  source: string
  date: string
  framework: string
  type: 'new_regulation' | 'amendment' | 'rts_its' | 'guidance' | 'enforcement'
  urgency: 'high' | 'medium' | 'low'
  summary: string
  eur_lex_url?: string
}

const TYPE_CONFIG: Record<string, { label: string; color: string }> = {
  new_regulation: { label: 'Nuova normativa', color: 'text-red-400 bg-red-400/10 border-red-400/20' },
  amendment: { label: 'Modifica', color: 'text-orange-400 bg-orange-400/10 border-orange-400/20' },
  rts_its: { label: 'RTS/ITS', color: 'text-blue-400 bg-blue-400/10 border-blue-400/20' },
  guidance: { label: 'Linee guida', color: 'text-purple-400 bg-purple-400/10 border-purple-400/20' },
  enforcement: { label: 'Enforcement', color: 'text-yellow-400 bg-yellow-400/10 border-yellow-400/20' },
}

const MOCK_UPDATES: RegUpdate[] = [
  {
    id: 'reg-001',
    title: 'Omnibus I Package: innalzamento soglie CSRD a 1.000 dipendenti',
    source: 'European Commission',
    date: '2026-02-26',
    framework: 'CSRD',
    type: 'amendment',
    urgency: 'high',
    summary: 'La Commissione propone di innalzare la soglia CSRD da 250 a 1.000 dipendenti, escludendo circa l\'80% delle aziende attualmente in scope. Periodo di consultazione aperto fino al 26 marzo 2026.',
  },
  {
    id: 'reg-002',
    title: 'DORA: EBA pubblica final RTS su ICT incident classification',
    source: 'European Banking Authority',
    date: '2026-02-20',
    framework: 'DORA',
    type: 'rts_its',
    urgency: 'high',
    summary: 'RTS finale sulla classificazione degli incidenti ICT e cyber threat. Definisce soglie di materialit\u00e0 e tempistiche di notifica. Applicabile dal Q3 2026.',
  },
  {
    id: 'reg-003',
    title: 'AI Act: pubblicati i primi standard armonizzati (CEN/CENELEC)',
    source: 'CEN-CENELEC',
    date: '2026-02-15',
    framework: 'AI_ACT',
    type: 'guidance',
    urgency: 'medium',
    summary: 'Primi standard armonizzati per conformit\u00e0 AI Act: risk management (ISO 42001), data quality, transparency documentation. Adozione volontaria da subito, obbligatoria dal 2027.',
  },
  {
    id: 'reg-004',
    title: 'NIS2: ENISA pubblica guidance su incident reporting',
    source: 'ENISA',
    date: '2026-02-10',
    framework: 'NIS2',
    type: 'guidance',
    urgency: 'medium',
    summary: 'Guida pratica per la notifica degli incidenti: format standard, soglie di significativit\u00e0, canali di comunicazione con le autorit\u00e0 competenti nazionali.',
  },
  {
    id: 'reg-005',
    title: 'GDPR: sanzione \u20ac1.2B a Meta per trasferimenti dati verso USA',
    source: 'Irish Data Protection Commission',
    date: '2026-02-05',
    framework: 'GDPR',
    type: 'enforcement',
    urgency: 'low',
    summary: 'Record sanction confermata per trasferimenti dati transfrontalieri non conformi post-Schrems II. Rilevante per aziende che usano cloud provider US-based.',
  },
  {
    id: 'reg-006',
    title: 'EU Taxonomy: nuovi criteri tecnici per settore trasporti e edilizia',
    source: 'European Commission',
    date: '2026-01-30',
    framework: 'TAXONOMY',
    type: 'amendment',
    urgency: 'medium',
    summary: 'Atto delegato supplementare con criteri tecnici di screening per attivit\u00e0 di trasporto e costruzione. Applicabile per reporting 2026.',
  },
  {
    id: 'reg-007',
    title: 'CSDDD: rinvio recepimento nazionale a 2028 per PMI in scope indiretto',
    source: 'Council of the EU',
    date: '2026-01-25',
    framework: 'CSDDD',
    type: 'amendment',
    urgency: 'medium',
    summary: 'Il Consiglio concede 12 mesi aggiuntivi per il recepimento nazionale degli obblighi CSDDD relativi alla supply chain per PMI in scope indiretto.',
  },
]

export default function RegulatoryFeedPage() {
  const [frameworkFilter, setFrameworkFilter] = useState<string>('all')
  const [typeFilter, setTypeFilter] = useState<string>('all')

  const filtered = MOCK_UPDATES.filter(u => {
    if (frameworkFilter !== 'all' && u.framework !== frameworkFilter) return false
    if (typeFilter !== 'all' && u.type !== typeFilter) return false
    return true
  })

  return (
    <div className="space-y-6 max-w-5xl">
      {/* Header */}
      <div>
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Rss size={20} className="text-accent" />
          Regulatory Feed
        </h2>
        <p className="text-sm text-slate-500">
          Aggiornamenti normativi automatici - EUR-Lex, EBA, ESMA, EIOPA, ENISA
        </p>
        <div className="flex items-center gap-2 mt-2">
          <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
          <span className="text-[10px] text-green-400 font-medium">Feed attivo - ultimo aggiornamento: {new Date().toLocaleDateString('it-IT')}</span>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
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
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          aria-label="Filtra per tipo aggiornamento"
          className="px-3 py-2 bg-surface border border-white/[0.06] rounded-lg text-sm text-slate-300 focus:outline-none"
        >
          <option value="all">Tutti i tipi</option>
          {Object.entries(TYPE_CONFIG).map(([k, v]) => (
            <option key={k} value={k}>{v.label}</option>
          ))}
        </select>
      </div>

      {/* Feed items */}
      <div className="space-y-3">
        {filtered.map(update => {
          const typeCfg = TYPE_CONFIG[update.type]
          const fwDef = FRAMEWORKS.find(f => f.value === update.framework)
          return (
            <div key={update.id} className="bg-surface border border-white/[0.06] rounded-xl p-5">
              <div className="flex items-start gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap mb-1.5">
                    <span className={`text-[10px] px-2 py-0.5 rounded border font-medium ${typeCfg.color}`}>
                      {typeCfg.label}
                    </span>
                    <span
                      className="text-[10px] px-1.5 py-0.5 rounded font-medium"
                      style={{ color: fwDef?.color, backgroundColor: `${fwDef?.color}15` }}
                    >
                      {update.framework}
                    </span>
                    {update.urgency === 'high' && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-400/10 text-red-400 border border-red-400/20 font-medium flex items-center gap-0.5">
                        <AlertTriangle size={9} /> Urgente
                      </span>
                    )}
                  </div>
                  <h3 className="text-sm font-medium text-slate-200">{update.title}</h3>
                  <p className="text-xs text-slate-400 mt-1.5 leading-relaxed">{update.summary}</p>
                  <div className="flex items-center gap-3 mt-2 text-[10px] text-slate-600">
                    <span className="flex items-center gap-1"><Clock size={10} /> {new Date(update.date).toLocaleDateString('it-IT')}</span>
                    <span>{update.source}</span>
                  </div>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {filtered.length === 0 && (
        <div className="py-12 text-center text-slate-500 text-sm">
          <Filter size={24} className="mx-auto mb-2 text-slate-600" />
          Nessun aggiornamento corrisponde ai filtri selezionati
        </div>
      )}

      <p className="text-[9px] text-slate-600 italic">
        Feed automatico da EUR-Lex, EBA, ESMA, EIOPA, ENISA. Tempo di aggiornamento target: &lt;48 ore dalla pubblicazione.
        Le sintesi sono generate da AI - verificare sempre con le fonti ufficiali.
      </p>
    </div>
  )
}
