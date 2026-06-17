'use client'

import { useState, useCallback } from 'react'
import { FRAMEWORKS } from '@/lib/types'
import { Layers, Download, Info, ChevronDown, ChevronUp, Check } from 'lucide-react'

// Cross-framework overlap data (which frameworks have shared obligations)
const OVERLAP_MATRIX: Record<string, Record<string, number>> = {
  DORA:     { DORA: 100, NIS2: 75, GDPR: 40, AI_ACT: 25, CSRD: 15, CSDDD: 10, TAXONOMY: 5 },
  NIS2:     { DORA: 75, NIS2: 100, GDPR: 50, AI_ACT: 20, CSRD: 10, CSDDD: 5, TAXONOMY: 5 },
  GDPR:     { DORA: 40, NIS2: 50, GDPR: 100, AI_ACT: 60, CSRD: 30, CSDDD: 25, TAXONOMY: 10 },
  AI_ACT:   { DORA: 25, NIS2: 20, GDPR: 60, AI_ACT: 100, CSRD: 15, CSDDD: 20, TAXONOMY: 10 },
  CSRD:     { DORA: 15, NIS2: 10, GDPR: 30, AI_ACT: 15, CSRD: 100, CSDDD: 70, TAXONOMY: 85 },
  CSDDD:    { DORA: 10, NIS2: 5, GDPR: 25, AI_ACT: 20, CSRD: 70, CSDDD: 100, TAXONOMY: 55 },
  TAXONOMY: { DORA: 5, NIS2: 5, GDPR: 10, AI_ACT: 10, CSRD: 85, CSDDD: 55, TAXONOMY: 100 },
}

const KEY_OVERLAPS = [
  {
    id: 'dora-nis2',
    title: 'DORA + NIS2: ICT Risk Management',
    frameworks: ['DORA', 'NIS2'],
    severity: 'HIGH',
    articles: 'DORA Art. 6-16 / NIS2 Art. 21',
    description: 'Entrambi richiedono un framework di gestione del rischio ICT, incident reporting e test di resilienza. DORA \u00e8 lex specialis per il settore finanziario, ma NIS2 si applica come baseline per tutti i settori essenziali.',
    shared_obligations: [
      'ICT risk management framework documentato',
      'Incident reporting entro 24-72 ore',
      'Test di resilienza periodici',
      'Gestione rischio terze parti ICT',
      'Governance e accountability a livello board',
    ],
    recommendation: 'Implementare un unico framework ICT risk che soddisfi entrambi i requisiti. Usare DORA come standard pi\u00f9 stringente dove applicabile.',
  },
  {
    id: 'gdpr-aiact',
    title: 'GDPR + AI Act: Data Protection in AI Systems',
    frameworks: ['GDPR', 'AI_ACT'],
    severity: 'HIGH',
    articles: 'GDPR Art. 22, 35 / AI Act Art. 9-10, 14',
    description: 'Il GDPR disciplina il trattamento dei dati personali, incluso il processo decisionale automatizzato. L\'AI Act aggiunge requisiti specifici per sistemi AI che trattano dati personali, inclusa la qualit\u00e0 dei dati di training.',
    shared_obligations: [
      'DPIA obbligatoria per sistemi AI ad alto rischio',
      'Diritto a non essere soggetti a decisioni automatizzate',
      'Trasparenza sul funzionamento dell\'AI (Art. 50 AI Act + Art. 13-14 GDPR)',
      'Supervisione umana significativa (human oversight)',
      'Qualit\u00e0 e governance dei dati di training',
    ],
    recommendation: 'Integrare la valutazione AI Act nella DPIA esistente. Un singolo registro dei trattamenti che includa anche i sistemi AI.',
  },
  {
    id: 'csrd-taxonomy',
    title: 'CSRD + EU Taxonomy: Sustainability Reporting',
    frameworks: ['CSRD', 'TAXONOMY'],
    severity: 'MEDIUM',
    articles: 'CSRD Art. 19a / Taxonomy Art. 8',
    description: 'La CSRD richiede reporting di sostenibilit\u00e0 secondo gli ESRS. La Taxonomy richiede disclosure specifica sulle attivit\u00e0 economiche allineate (KPI: turnover, CapEx, OpEx). I due framework sono strettamente interconnessi.',
    shared_obligations: [
      'Double materiality assessment',
      'Disclosure KPI: percentuale fatturato/CapEx/OpEx taxonomy-aligned',
      'Reporting su climate change mitigation e adaptation',
      'Verifica da parte di auditor indipendente',
      'Pubblicazione nel management report',
    ],
    recommendation: 'Implementare il reporting CSRD e Taxonomy in parallelo. La Taxonomy disclosure \u00e8 un sotto-insieme obbligatorio del reporting CSRD.',
  },
  {
    id: 'csrd-csddd',
    title: 'CSRD + CSDDD: Supply Chain Due Diligence',
    frameworks: ['CSRD', 'CSDDD'],
    severity: 'MEDIUM',
    articles: 'CSRD ESRS S1-S4 / CSDDD Art. 6-11',
    description: 'La CSRD richiede disclosure sugli impatti nella catena del valore (ESRS S1-S4). La CSDDD richiede due diligence attiva e rimedi. La CSRD "report", la CSDDD "agisci".',
    shared_obligations: [
      'Identificazione impatti negativi nella value chain',
      'Due diligence su diritti umani e ambiente',
      'Piano di transizione climatica',
      'Meccanismi di reclamo (grievance mechanisms)',
      'Reporting pubblico sui risultati della due diligence',
    ],
    recommendation: 'Un unico processo di due diligence che soddisfi sia l\'obbligo di reporting CSRD che l\'obbligo di azione CSDDD.',
  },
]

export default function CrossFrameworkPage() {
  const [expandedOverlap, setExpandedOverlap] = useState<string | null>(KEY_OVERLAPS[0].id)
  const [exported, setExported] = useState(false)
  const frameworks = ['DORA', 'NIS2', 'GDPR', 'AI_ACT', 'CSRD', 'CSDDD', 'TAXONOMY']

  const handleExport = useCallback(() => {
    const lines = [
      'CROSS-FRAMEWORK INTELLIGENCE REPORT',
      `NormaAI - ${new Date().toLocaleDateString('it-IT', { day: 'numeric', month: 'long', year: 'numeric' })}`,
      '',
      '═══════════════════════════════════════════════════',
      'MATRICE SOVRAPPOSIZIONI (% obblighi condivisi)',
      '═══════════════════════════════════════════════════',
      '',
      ['', ...frameworks].join('\t'),
      ...frameworks.map(row =>
        [row, ...frameworks.map(col => `${OVERLAP_MATRIX[row]?.[col] ?? 0}%`)].join('\t')
      ),
      '',
      '═══════════════════════════════════════════════════',
      'SOVRAPPOSIZIONI CHIAVE',
      '═══════════════════════════════════════════════════',
      '',
      ...KEY_OVERLAPS.flatMap(o => [
        `▸ ${o.title} [${o.severity}]`,
        `  Articoli: ${o.articles}`,
        `  ${o.description}`,
        '  Obblighi condivisi:',
        ...o.shared_obligations.map(ob => `    • ${ob}`),
        `  Raccomandazione: ${o.recommendation}`,
        '',
      ]),
      '═══════════════════════════════════════════════════',
      'Generato da NormaAI - Le percentuali sono stime indicative.',
      'Consultare un professionista qualificato per valutazioni vincolanti.',
    ]
    const blob = new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `cross-framework-report-${new Date().toISOString().slice(0, 10)}.txt`
    a.click()
    URL.revokeObjectURL(url)
    setExported(true)
    setTimeout(() => setExported(false), 2500)
  }, [])

  const getOverlapColor = (value: number) => {
    if (value >= 100) return 'bg-accent/20 text-accent'
    if (value >= 70) return 'bg-red-400/15 text-red-400'
    if (value >= 40) return 'bg-orange-400/15 text-orange-400'
    if (value >= 20) return 'bg-yellow-400/15 text-yellow-400'
    if (value >= 10) return 'bg-slate-400/10 text-slate-500'
    return 'bg-transparent text-slate-700'
  }

  return (
    <div className="space-y-6 max-w-6xl">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Layers size={20} className="text-accent" />
            Cross-Framework Intelligence
          </h2>
          <p className="text-sm text-slate-500">
            Analisi sovrapposizioni normative - identifica obblighi condivisi tra framework EU
          </p>
        </div>
        <button
          onClick={handleExport}
          className={`px-4 py-2 text-sm rounded-lg transition flex items-center gap-2 ${
            exported
              ? 'bg-green-500/10 border border-green-500/20 text-green-400'
              : 'bg-surface border border-white/[0.06] text-slate-300 hover:text-white hover:border-accent/30'
          }`}
        >
          {exported ? <><Check size={14} /> Esportato</> : <><Download size={14} /> Export Report</>}
        </button>
      </div>

      {/* Overlap Matrix */}
      <div className="bg-surface border border-white/[0.06] rounded-xl p-5 overflow-x-auto">
        <h3 className="text-xs uppercase tracking-widest text-slate-500 font-semibold mb-4">
          Matrice Sovrapposizioni (% obblighi condivisi)
        </h3>
        <table className="w-full text-xs">
          <thead>
            <tr>
              <th className="px-2 py-2 text-left text-slate-500 font-medium w-20"></th>
              {frameworks.map(fw => (
                <th key={fw} className="px-2 py-2 text-center text-slate-400 font-medium">{fw.replace('_', ' ')}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {frameworks.map(row => (
              <tr key={row}>
                <td className="px-2 py-2 text-slate-400 font-medium">{row.replace('_', ' ')}</td>
                {frameworks.map(col => {
                  const value = OVERLAP_MATRIX[row]?.[col] ?? 0
                  return (
                    <td key={col} className="px-1 py-1 text-center">
                      <div className={`rounded px-2 py-1.5 font-mono font-medium text-[11px] ${getOverlapColor(value)}`}>
                        {value === 100 ? '\u2014' : `${value}%`}
                      </div>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
        <div className="flex items-center gap-4 mt-3 pt-3 border-t border-white/[0.04] text-[10px] text-slate-500">
          <span className="flex items-center gap-1"><div className="w-3 h-3 rounded bg-red-400/15" /> Alto (70%+)</span>
          <span className="flex items-center gap-1"><div className="w-3 h-3 rounded bg-orange-400/15" /> Medio (40-69%)</span>
          <span className="flex items-center gap-1"><div className="w-3 h-3 rounded bg-yellow-400/15" /> Basso (20-39%)</span>
          <span className="flex items-center gap-1"><div className="w-3 h-3 rounded bg-slate-400/10" /> Minimo (&lt;20%)</span>
        </div>
      </div>

      {/* Key Overlaps */}
      <div className="space-y-3">
        <h3 className="text-xs uppercase tracking-widest text-slate-500 font-semibold flex items-center gap-2">
          <Info size={14} /> Sovrapposizioni Chiave
        </h3>
        {KEY_OVERLAPS.map(overlap => {
          const isExpanded = expandedOverlap === overlap.id
          return (
            <div key={overlap.id} className="bg-surface border border-white/[0.06] rounded-xl overflow-hidden">
              <button
                onClick={() => setExpandedOverlap(isExpanded ? null : overlap.id)}
                className="w-full px-5 py-4 flex items-center gap-3 hover:bg-white/[0.02] transition text-left"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium">{overlap.title}</span>
                    <span className={`text-[9px] px-1.5 py-0.5 rounded font-semibold ${
                      overlap.severity === 'HIGH'
                        ? 'bg-red-400/10 text-red-400 border border-red-400/20'
                        : 'bg-yellow-400/10 text-yellow-400 border border-yellow-400/20'
                    }`}>
                      {overlap.severity}
                    </span>
                  </div>
                  <div className="text-[10px] text-slate-500 mt-0.5 font-mono">{overlap.articles}</div>
                </div>
                <div className="flex gap-1 shrink-0">
                  {overlap.frameworks.map(fw => {
                    const fwDef = FRAMEWORKS.find(f => f.value === fw)
                    return (
                      <span key={fw} className="text-[10px] px-1.5 py-0.5 rounded font-medium" style={{ color: fwDef?.color, backgroundColor: `${fwDef?.color}15` }}>
                        {fw}
                      </span>
                    )
                  })}
                </div>
                {isExpanded ? <ChevronUp size={14} className="text-slate-500 shrink-0" /> : <ChevronDown size={14} className="text-slate-500 shrink-0" />}
              </button>

              {isExpanded && (
                <div className="px-5 pb-5 border-t border-white/[0.04] space-y-3">
                  <p className="text-xs text-slate-300 leading-relaxed pt-3">{overlap.description}</p>

                  <div>
                    <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-2">Obblighi Condivisi</div>
                    <div className="space-y-1">
                      {overlap.shared_obligations.map((ob, i) => (
                        <div key={i} className="flex items-start gap-2 text-xs text-slate-400">
                          <span className="text-accent mt-0.5">&#8226;</span>
                          {ob}
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="bg-accent/5 border border-accent/10 rounded-lg px-3 py-2">
                    <div className="text-[10px] uppercase tracking-wider text-accent font-semibold mb-1">Raccomandazione</div>
                    <p className="text-xs text-slate-300">{overlap.recommendation}</p>
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* AI disclaimer */}
      <p className="text-[9px] text-slate-600 italic">
        Analisi delle sovrapposizioni generata da AI basata sulle fonti normative disponibili. Le percentuali di sovrapposizione sono stime indicative.
        Consultare un professionista qualificato per una valutazione completa delle interazioni tra framework.
      </p>
    </div>
  )
}
