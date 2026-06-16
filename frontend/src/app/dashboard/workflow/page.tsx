'use client'

import { useState, useMemo, useEffect, useCallback } from 'react'
import { DEMO_WORKFLOW_ITEMS } from '@/lib/mock-data'
import type { WorkflowItem, WorkflowStatus } from '@/lib/types'
import {
  GitPullRequest,
  CheckCircle,
  XCircle,
  Clock,
  User,
  AlertTriangle,
  Filter,
} from 'lucide-react'

// ─── Status Configuration ───────────────────────────────────

const STATUS_CONFIG: Record<WorkflowStatus, { label: string; color: string }> = {
  ai_generated: { label: 'AI Generated', color: 'text-purple-400 bg-purple-400/10 border-purple-400/20' },
  under_review: { label: 'In Review', color: 'text-yellow-400 bg-yellow-400/10 border-yellow-400/20' },
  validated: { label: 'Validato', color: 'text-blue-400 bg-blue-400/10 border-blue-400/20' },
  approved: { label: 'Approvato', color: 'text-green-400 bg-green-400/10 border-green-400/20' },
  rejected: { label: 'Rifiutato', color: 'text-red-400 bg-red-400/10 border-red-400/20' },
}

const PRIORITY_CONFIG: Record<string, string> = {
  P1: 'text-red-400 bg-red-400/10 border-red-400/20',
  P2: 'text-orange-400 bg-orange-400/10 border-orange-400/20',
  P3: 'text-yellow-400 bg-yellow-400/10 border-yellow-400/20',
  P4: 'text-slate-400 bg-slate-400/10 border-slate-400/20',
}

const SOURCE_LABELS: Record<string, string> = {
  gap_analysis: 'Gap Analysis',
  monitor: 'Monitor',
  qa: 'Q&A',
}

const FRAMEWORKS = ['DORA', 'CSRD', 'NIS2', 'AI_ACT', 'GDPR', 'CSDDD', 'TAXONOMY'] as const

const STORAGE_KEY = 'normaai-workflow-items'

// ─── Helpers ────────────────────────────────────────────────

function loadWorkflowItems(): WorkflowItem[] {
  if (typeof window === 'undefined') return DEMO_WORKFLOW_ITEMS
  try {
    const stored = sessionStorage.getItem(STORAGE_KEY)
    if (stored) return JSON.parse(stored) as WorkflowItem[]
  } catch {
    // ignore
  }
  return DEMO_WORKFLOW_ITEMS
}

function saveWorkflowItems(items: WorkflowItem[]) {
  if (typeof window === 'undefined') return
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(items))
  } catch {
    // ignore
  }
}

function daysUntil(dateStr: string | null): number | null {
  if (!dateStr) return null
  const diff = new Date(dateStr).getTime() - Date.now()
  return Math.ceil(diff / (1000 * 60 * 60 * 24))
}

// ─── Page Component ─────────────────────────────────────────

export default function WorkflowPage() {
  const [items, setItems] = useState<WorkflowItem[]>([])
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [frameworkFilter, setFrameworkFilter] = useState<string>('all')
  const [priorityFilter, setPriorityFilter] = useState<string>('all')
  const [mounted, setMounted] = useState(false)

  // Load from sessionStorage on mount
  useEffect(() => {
    setItems(loadWorkflowItems())
    setMounted(true)
  }, [])

  // Persist changes
  const updateItems = useCallback((newItems: WorkflowItem[]) => {
    setItems(newItems)
    saveWorkflowItems(newItems)
  }, [])

  // ─── Actions ──────────────────────────────────────────────

  const handleTakeOwnership = useCallback((id: string) => {
    updateItems(
      items.map(item =>
        item.id === id
          ? {
              ...item,
              status: 'under_review' as WorkflowStatus,
              assigned_to: 'demo-user-001',
              assigned_to_name: 'Demo User',
              updated_at: new Date().toISOString(),
              approval_chain: item.approval_chain.map((step, i) =>
                i === 0 ? { ...step, user: 'Demo User', status: 'approved' as const, date: new Date().toISOString() } : step
              ),
            }
          : item
      )
    )
  }, [items, updateItems])

  const handleApprove = useCallback((id: string) => {
    updateItems(
      items.map(item => {
        if (item.id !== id) return item
        // Find first pending step and approve it
        const chain = [...item.approval_chain]
        const pendingIdx = chain.findIndex(s => s.status === 'pending')
        if (pendingIdx >= 0) {
          chain[pendingIdx] = {
            ...chain[pendingIdx],
            user: chain[pendingIdx].user || 'Demo User',
            status: 'approved',
            date: new Date().toISOString(),
          }
        }
        // Determine new status
        const allApproved = chain.every(s => s.status === 'approved')
        const lastPendingWasTeamLead = pendingIdx === 1
        let newStatus: WorkflowStatus = item.status
        if (allApproved) newStatus = 'approved'
        else if (lastPendingWasTeamLead || pendingIdx >= 1) newStatus = 'validated'
        else newStatus = 'under_review'

        return { ...item, status: newStatus, approval_chain: chain, updated_at: new Date().toISOString() }
      })
    )
  }, [items, updateItems])

  const handleReject = useCallback((id: string) => {
    updateItems(
      items.map(item =>
        item.id === id
          ? {
              ...item,
              status: 'rejected' as WorkflowStatus,
              updated_at: new Date().toISOString(),
              approval_chain: item.approval_chain.map(step =>
                step.status === 'pending'
                  ? { ...step, user: step.user || 'Demo User', status: 'rejected' as const, date: new Date().toISOString() }
                  : step
              ),
            }
          : item
      )
    )
  }, [items, updateItems])

  // ─── Filtering ────────────────────────────────────────────

  const filtered = useMemo(() => {
    let result = [...items]
    if (statusFilter !== 'all') result = result.filter(i => i.status === statusFilter)
    if (frameworkFilter !== 'all') result = result.filter(i => i.framework === frameworkFilter)
    if (priorityFilter !== 'all') result = result.filter(i => i.priority === priorityFilter)
    return result
  }, [items, statusFilter, frameworkFilter, priorityFilter])

  // ─── Summary counts ──────────────────────────────────────

  const counts = useMemo(() => {
    const c = { ai_generated: 0, under_review: 0, validated: 0, approved: 0, rejected: 0 }
    for (const item of items) {
      c[item.status]++
    }
    return c
  }, [items])

  const needsReview = counts.ai_generated + counts.under_review + counts.validated

  // SSR guard
  if (!mounted) {
    return (
      <div className="space-y-6 max-w-6xl">
        <div className="h-8 w-64 bg-surface rounded animate-pulse" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="h-20 bg-surface rounded-xl animate-pulse" />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-6xl">
      {/* Header */}
      <div>
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <GitPullRequest size={20} className="text-accent" /> Review Queue
          {needsReview > 0 && (
            <span className="ml-2 text-xs px-2 py-0.5 rounded-full bg-yellow-400/10 text-yellow-400 border border-yellow-400/20 font-medium">
              {needsReview} da revisionare
            </span>
          )}
        </h2>
        <p className="text-sm text-slate-500">
          Workflow di approvazione per finding AI &mdash; dal rilevamento alla validazione finale
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {([
          { key: 'ai_generated', label: 'AI Generated', icon: AlertTriangle, accent: 'text-purple-400' },
          { key: 'under_review', label: 'In Review', icon: Clock, accent: 'text-yellow-400' },
          { key: 'validated', label: 'Validati', icon: CheckCircle, accent: 'text-blue-400' },
          { key: 'approved', label: 'Approvati', icon: CheckCircle, accent: 'text-green-400' },
        ] as const).map(card => (
          <button
            key={card.key}
            onClick={() => setStatusFilter(statusFilter === card.key ? 'all' : card.key)}
            className={`bg-surface border rounded-xl px-4 py-3 text-left transition hover:border-white/10 ${
              statusFilter === card.key ? 'border-accent/30 bg-accent/5' : 'border-white/[0.06]'
            }`}
          >
            <div className="flex items-center gap-2 mb-1">
              <card.icon size={14} className={card.accent} />
              <span className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">{card.label}</span>
            </div>
            <div className={`text-2xl font-bold ${card.accent}`}>
              {counts[card.key]}
            </div>
          </button>
        ))}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          aria-label="Filtra per stato"
          className="px-3 py-2 bg-surface border border-white/[0.06] rounded-lg text-sm text-slate-300 focus:outline-none"
        >
          <option value="all">Tutti gli stati</option>
          {Object.entries(STATUS_CONFIG).map(([key, cfg]) => (
            <option key={key} value={key}>{cfg.label}</option>
          ))}
        </select>

        <select
          value={frameworkFilter}
          onChange={(e) => setFrameworkFilter(e.target.value)}
          aria-label="Filtra per framework"
          className="px-3 py-2 bg-surface border border-white/[0.06] rounded-lg text-sm text-slate-300 focus:outline-none"
        >
          <option value="all">Tutti i framework</option>
          {FRAMEWORKS.map(fw => (
            <option key={fw} value={fw}>{fw}</option>
          ))}
        </select>

        <select
          value={priorityFilter}
          onChange={(e) => setPriorityFilter(e.target.value)}
          aria-label="Filtra per priorita"
          className="px-3 py-2 bg-surface border border-white/[0.06] rounded-lg text-sm text-slate-300 focus:outline-none"
        >
          <option value="all">Tutte le priorit&agrave;</option>
          <option value="P1">P1 - Critica</option>
          <option value="P2">P2 - Alta</option>
          <option value="P3">P3 - Media</option>
          <option value="P4">P4 - Bassa</option>
        </select>

        {(statusFilter !== 'all' || frameworkFilter !== 'all' || priorityFilter !== 'all') && (
          <button
            onClick={() => { setStatusFilter('all'); setFrameworkFilter('all'); setPriorityFilter('all') }}
            className="px-3 py-2 text-sm text-slate-400 hover:text-white transition flex items-center gap-1"
          >
            <XCircle size={14} /> Reset filtri
          </button>
        )}
      </div>

      {/* Results count */}
      <div className="text-xs text-slate-500">
        {filtered.length} item{filtered.length !== 1 ? 's' : ''}{' '}
        {filtered.length !== items.length && `(filtrati da ${items.length})`}
      </div>

      {/* Item Cards */}
      <div className="space-y-3">
        {filtered.map(item => {
          const statusCfg = STATUS_CONFIG[item.status]
          const priorityCfg = PRIORITY_CONFIG[item.priority] || PRIORITY_CONFIG.P4
          const days = daysUntil(item.deadline)
          const isUrgent = days !== null && days <= 14
          const isOverdue = days !== null && days < 0

          return (
            <div
              key={item.id}
              className="bg-surface border border-white/[0.06] rounded-xl p-5 hover:border-white/10 transition"
            >
              {/* Top row: title + badges */}
              <div className="flex items-start justify-between gap-4 mb-3">
                <div className="flex-1 min-w-0">
                  <h3 className="text-sm font-semibold text-slate-200 mb-1">{item.title}</h3>
                  <p className="text-xs text-slate-500 line-clamp-2">{item.description}</p>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <span className={`text-[10px] px-2 py-0.5 rounded border font-medium ${priorityCfg}`}>
                    {item.priority}
                  </span>
                  <span className={`text-[10px] px-2 py-0.5 rounded border font-medium ${statusCfg.color}`}>
                    {statusCfg.label}
                  </span>
                </div>
              </div>

              {/* Meta row */}
              <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mb-4 text-xs text-slate-400">
                <span className="px-1.5 py-0.5 rounded bg-accent/10 text-accent font-medium text-[10px]">
                  {item.framework}
                </span>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.04] text-slate-500">
                  {SOURCE_LABELS[item.source] || item.source}
                </span>
                <span className="flex items-center gap-1">
                  <User size={12} className="text-slate-600" />
                  {item.assigned_to_name || 'Non assegnato'}
                </span>
                <span className="text-slate-600">{item.client_name}</span>
                {item.deadline && (
                  <span className={`flex items-center gap-1 ${isOverdue ? 'text-red-400' : isUrgent ? 'text-yellow-400' : 'text-slate-400'}`}>
                    <Clock size={12} />
                    {isOverdue
                      ? `Scaduto ${Math.abs(days!)}g fa`
                      : `${days}g rimanenti`}
                    <span className="text-slate-600 ml-1">
                      ({new Date(item.deadline).toLocaleDateString('it-IT', { day: '2-digit', month: 'short' })})
                    </span>
                  </span>
                )}
              </div>

              {/* Approval chain + actions */}
              <div className="flex items-center justify-between gap-4">
                {/* Approval chain visualization */}
                <div className="flex items-center gap-1">
                  {item.approval_chain.map((step, i) => (
                    <div key={i} className="flex items-center gap-1">
                      {i > 0 && <div className="w-4 h-px bg-white/[0.08]" />}
                      <div className="flex items-center gap-1.5" title={`${step.role}: ${step.user || 'Non assegnato'} - ${step.status}`}>
                        {step.status === 'approved' ? (
                          <CheckCircle size={14} className="text-green-400" />
                        ) : step.status === 'rejected' ? (
                          <XCircle size={14} className="text-red-400" />
                        ) : (
                          <div className="w-3.5 h-3.5 rounded-full border border-slate-600 bg-transparent" />
                        )}
                        <span className="text-[10px] text-slate-500 hidden sm:inline">{step.role}</span>
                      </div>
                    </div>
                  ))}
                </div>

                {/* Action buttons */}
                <div className="flex items-center gap-2 flex-shrink-0">
                  {item.status === 'ai_generated' && (
                    <button
                      onClick={() => handleTakeOwnership(item.id)}
                      aria-label="Prendi in carico questo finding"
                      className="px-3 py-1.5 text-xs font-medium bg-purple-500/10 text-purple-400 border border-purple-500/20 rounded-lg hover:bg-purple-500/20 transition"
                    >
                      Prendi in carico
                    </button>
                  )}
                  {(item.status === 'under_review' || item.status === 'validated') && (
                    <>
                      <button
                        onClick={() => handleReject(item.id)}
                        aria-label="Rifiuta questo finding"
                        className="px-3 py-1.5 text-xs font-medium bg-red-500/10 text-red-400 border border-red-500/20 rounded-lg hover:bg-red-500/20 transition"
                      >
                        Rifiuta
                      </button>
                      <button
                        onClick={() => handleApprove(item.id)}
                        aria-label="Approva questo finding"
                        className="px-3 py-1.5 text-xs font-medium bg-green-500/10 text-green-400 border border-green-500/20 rounded-lg hover:bg-green-500/20 transition"
                      >
                        Approva
                      </button>
                    </>
                  )}
                  {item.status === 'approved' && (
                    <span className="text-[10px] text-green-400/60 flex items-center gap-1">
                      <CheckCircle size={12} /> Completato
                    </span>
                  )}
                  {item.status === 'rejected' && (
                    <span className="text-[10px] text-red-400/60 flex items-center gap-1">
                      <XCircle size={12} /> Rifiutato
                    </span>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Empty state */}
      {filtered.length === 0 && (
        <div className="py-12 text-center text-slate-500 text-sm">
          <Filter size={24} className="mx-auto mb-2 text-slate-600" />
          Nessun item corrisponde ai filtri selezionati
        </div>
      )}

      {/* Footer note */}
      <p className="text-[9px] text-slate-600 italic">
        I finding AI vengono generati automaticamente dalle analisi di gap, monitoring e Q&amp;A.
        Ogni item deve passare attraverso la catena di approvazione prima di essere considerato validato.
      </p>
    </div>
  )
}
