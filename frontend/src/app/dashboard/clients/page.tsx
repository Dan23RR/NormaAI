'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import type { Framework, CompanyProfile } from '@/lib/types'
import { FRAMEWORKS } from '@/lib/types'
import { Building2, Plus, Pencil, Trash2, Search, Users, X, AlertTriangle, Loader2 } from 'lucide-react'

interface Client {
  id: string
  name: string
  sector: string
  employee_count: number
  revenue_eur: number
  jurisdictions: string[]
  applicable_frameworks: string[]
}

type ClientForm = Omit<Client, 'id'>

const emptyForm: ClientForm = {
  name: '',
  sector: '',
  employee_count: 0,
  revenue_eur: 0,
  jurisdictions: [],
  applicable_frameworks: [],
}

export default function ClientsPage() {
  const router = useRouter()
  const [clients, setClients] = useState<Client[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')

  // Modal state
  const [showModal, setShowModal] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState<ClientForm>({ ...emptyForm })
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState('')

  // Delete state
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const fetchClients = useCallback(async () => {
    try {
      const res = await api.get<{ data: Client[] } | Client[]>('/api/v1/clients')
      setClients(Array.isArray(res) ? res : (res as { data: Client[] }).data ?? [])
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load clients')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchClients()
  }, [fetchClients])

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && showModal) setShowModal(false)
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [showModal])

  const filteredClients = clients.filter(c =>
    c.name.toLowerCase().includes(search.toLowerCase())
  )

  const openCreate = () => {
    setEditingId(null)
    setForm({ ...emptyForm })
    setFormError('')
    setShowModal(true)
  }

  const openEdit = (client: Client) => {
    setEditingId(client.id)
    setForm({
      name: client.name,
      sector: client.sector,
      employee_count: client.employee_count,
      revenue_eur: client.revenue_eur,
      jurisdictions: client.jurisdictions,
      applicable_frameworks: client.applicable_frameworks,
    })
    setFormError('')
    setShowModal(true)
  }

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.name.trim()) {
      setFormError('Il nome del cliente è obbligatorio')
      return
    }

    setFormError('')
    setSaving(true)

    try {
      if (editingId) {
        await api.put(`/api/v1/clients/${editingId}`, form)
      } else {
        await api.post('/api/v1/clients', form)
      }
      setShowModal(false)
      setEditingId(null)
      fetchClients()
    } catch (err: unknown) {
      setFormError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id: string) => {
    if (!window.confirm('Sei sicuro di voler eliminare questo cliente?')) return
    setDeletingId(id)
    try {
      await api.del(`/api/v1/clients/${id}`)
      setClients(prev => prev.filter(c => c.id !== id))
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Delete failed')
    } finally {
      setDeletingId(null)
    }
  }

  const updateForm = (field: keyof ClientForm, value: unknown) => {
    setForm(prev => ({ ...prev, [field]: value }))
  }

  const toggleFramework = (fw: string) => {
    setForm(prev => ({
      ...prev,
      applicable_frameworks: prev.applicable_frameworks.includes(fw)
        ? prev.applicable_frameworks.filter(f => f !== fw)
        : [...prev.applicable_frameworks, fw],
    }))
  }

  return (
    <div className="space-y-6 max-w-6xl">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search clients..."
            className="w-full pl-9 pr-3 py-2.5 bg-surface border border-white/[0.06] rounded-lg text-sm text-white focus:outline-none focus:border-accent/40 transition"
          />
        </div>
        <button
          type="button"
          onClick={openCreate}
          className="px-4 py-2.5 rounded-lg bg-gradient-to-r from-accent to-accent2 text-white font-medium hover:opacity-90 transition flex items-center gap-2 text-sm shrink-0"
        >
          <Plus size={16} />
          Add Client
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm flex items-center gap-2">
          <AlertTriangle size={16} /> {error}
          <button type="button" onClick={() => setError('')} className="ml-auto text-red-400 hover:text-red-300">
            <X size={14} />
          </button>
        </div>
      )}

      {/* Client table */}
      <div className="bg-surface border border-white/[0.06] rounded-xl overflow-hidden">
        {loading ? (
          <div className="p-8 space-y-3">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-12 bg-surface2 rounded animate-pulse" />
            ))}
          </div>
        ) : filteredClients.length === 0 ? (
          <div className="py-16 text-center">
            <Building2 size={40} className="mx-auto mb-3 text-slate-600" />
            <h3 className="text-sm font-medium text-slate-400 mb-1">
              {search ? 'No clients match your search' : 'No clients yet'}
            </h3>
            <p className="text-xs text-slate-500 mb-4">
              {search ? 'Try a different search term.' : 'Add your first client to get started.'}
            </p>
            {!search && (
              <button
                type="button"
                onClick={openCreate}
                className="px-4 py-2 rounded-lg border border-accent/40 text-accent text-sm hover:bg-accent/10 transition"
              >
                <Plus size={14} className="inline mr-1" />
                Add Client
              </button>
            )}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-slate-500 text-left text-xs border-b border-white/[0.06]">
                  <th className="px-5 py-3 font-medium">Name</th>
                  <th className="px-5 py-3 font-medium">Sector</th>
                  <th className="px-5 py-3 font-medium">Employees</th>
                  <th className="px-5 py-3 font-medium">Revenue (EUR)</th>
                  <th className="px-5 py-3 font-medium">Frameworks</th>
                  <th className="px-5 py-3 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.04]">
                {filteredClients.map(client => (
                  <tr key={client.id} className="hover:bg-white/[0.02] transition cursor-pointer" onClick={() => router.push(`/dashboard/clients/${client.id}`)}>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2">
                        <Building2 size={14} className="text-accent shrink-0" />
                        <span className="font-medium text-slate-200">{client.name}</span>
                      </div>
                    </td>
                    <td className="px-5 py-3 text-slate-400">{client.sector || '-'}</td>
                    <td className="px-5 py-3 text-slate-400">
                      <span className="flex items-center gap-1">
                        <Users size={12} className="text-slate-500" />
                        {client.employee_count ? client.employee_count.toLocaleString() : '-'}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-slate-400">
                      {client.revenue_eur ? `${(client.revenue_eur / 1_000_000).toFixed(1)}M` : '-'}
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex flex-wrap gap-1">
                        {client.applicable_frameworks.length > 0 ? (
                          client.applicable_frameworks.map(fw => {
                            const fwDef = FRAMEWORKS.find(f => f.value === fw)
                            return (
                              <span
                                key={fw}
                                className="text-[10px] px-1.5 py-0.5 rounded border border-white/[0.08] font-medium"
                                style={{ color: fwDef?.color ?? '#94a3b8' }}
                              >
                                {fw}
                              </span>
                            )
                          })
                        ) : (
                          <span className="text-slate-600 text-xs">None</span>
                        )}
                      </div>
                    </td>
                    <td className="px-5 py-3 text-right">
                      <div className="flex items-center justify-end gap-1" onClick={(e) => e.stopPropagation()}>
                        <button
                          type="button"
                          onClick={() => openEdit(client)}
                          className="p-1.5 rounded hover:bg-white/[0.06] text-slate-400 hover:text-accent transition"
                          title="Edit"
                        >
                          <Pencil size={14} />
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDelete(client.id)}
                          disabled={deletingId === client.id}
                          className="p-1.5 rounded hover:bg-red-500/10 text-slate-400 hover:text-red-400 transition disabled:opacity-50"
                          title="Delete"
                        >
                          {deletingId === client.id ? (
                            <Loader2 size={14} className="animate-spin" />
                          ) : (
                            <Trash2 size={14} />
                          )}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Client count */}
      {!loading && clients.length > 0 && (
        <div className="text-xs text-slate-500 text-right">
          {filteredClients.length} of {clients.length} client{clients.length !== 1 ? 's' : ''}
        </div>
      )}

      {/* Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="client-modal-title">
          <div className="bg-surface border border-white/[0.06] rounded-xl w-full max-w-lg mx-4 shadow-2xl">
            {/* Modal header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-white/[0.06]">
              <h2 id="client-modal-title" className="text-sm font-semibold text-white">
                {editingId ? 'Edit Client' : 'Add New Client'}
              </h2>
              <button
                type="button"
                onClick={() => setShowModal(false)}
                className="p-1 rounded hover:bg-white/[0.06] text-slate-400 hover:text-white transition"
              >
                <X size={16} />
              </button>
            </div>

            {/* Modal form */}
            <form onSubmit={handleSave} className="p-5 space-y-4">
              {formError && (
                <div className="p-2.5 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-xs flex items-center gap-2">
                  <AlertTriangle size={14} /> {formError}
                </div>
              )}

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="sm:col-span-2">
                  <label htmlFor="cl-name" className="block text-xs text-slate-500 mb-1">
                    Company name <span className="text-red-400">*</span>
                  </label>
                  <input
                    id="cl-name"
                    type="text"
                    value={form.name}
                    onChange={(e) => updateForm('name', e.target.value)}
                    required
                    maxLength={200}
                    className="w-full px-3 py-2 bg-surface2 border border-white/[0.06] rounded-lg text-sm text-white focus:outline-none focus:border-accent/40 transition"
                    placeholder="Acme Srl"
                  />
                </div>
                <div>
                  <label htmlFor="cl-sector" className="block text-xs text-slate-500 mb-1">Sector</label>
                  <input
                    id="cl-sector"
                    type="text"
                    value={form.sector}
                    onChange={(e) => updateForm('sector', e.target.value)}
                    maxLength={100}
                    className="w-full px-3 py-2 bg-surface2 border border-white/[0.06] rounded-lg text-sm text-white focus:outline-none focus:border-accent/40 transition"
                    placeholder="Manufacturing"
                  />
                </div>
                <div>
                  <label htmlFor="cl-employees" className="block text-xs text-slate-500 mb-1">Employees</label>
                  <input
                    id="cl-employees"
                    type="number"
                    value={form.employee_count || ''}
                    onChange={(e) => updateForm('employee_count', Math.max(0, parseInt(e.target.value) || 0))}
                    min={0}
                    className="w-full px-3 py-2 bg-surface2 border border-white/[0.06] rounded-lg text-sm text-white focus:outline-none focus:border-accent/40 transition"
                    placeholder="2500"
                  />
                </div>
                <div>
                  <label htmlFor="cl-revenue" className="block text-xs text-slate-500 mb-1">Revenue (EUR)</label>
                  <input
                    id="cl-revenue"
                    type="number"
                    value={form.revenue_eur || ''}
                    onChange={(e) => updateForm('revenue_eur', Math.max(0, parseInt(e.target.value) || 0))}
                    min={0}
                    className="w-full px-3 py-2 bg-surface2 border border-white/[0.06] rounded-lg text-sm text-white focus:outline-none focus:border-accent/40 transition"
                    placeholder="200000000"
                  />
                </div>
                <div>
                  <label htmlFor="cl-jurisdictions" className="block text-xs text-slate-500 mb-1">Jurisdictions (comma-separated)</label>
                  <input
                    id="cl-jurisdictions"
                    type="text"
                    value={form.jurisdictions.join(', ')}
                    onChange={(e) => updateForm('jurisdictions', e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                    className="w-full px-3 py-2 bg-surface2 border border-white/[0.06] rounded-lg text-sm text-white focus:outline-none focus:border-accent/40 transition"
                    placeholder="IT, DE, FR"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs text-slate-500 mb-2">Applicable frameworks</label>
                <div className="flex flex-wrap gap-2" role="group" aria-label="Framework selection">
                  {FRAMEWORKS.map(fw => {
                    const selected = form.applicable_frameworks.includes(fw.value)
                    return (
                      <button
                        key={fw.value}
                        type="button"
                        onClick={() => toggleFramework(fw.value)}
                        className={`px-2.5 py-1 rounded-md text-xs font-medium border transition ${
                          selected
                            ? 'border-accent/40 bg-accent/10 text-accent'
                            : 'border-white/[0.06] text-slate-500 hover:text-slate-300'
                        }`}
                        aria-pressed={selected}
                      >
                        {fw.value}
                      </button>
                    )
                  })}
                </div>
              </div>

              {/* Modal actions */}
              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="px-4 py-2 rounded-lg border border-white/[0.06] text-slate-400 text-sm hover:text-white hover:border-white/10 transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="px-5 py-2 rounded-lg bg-gradient-to-r from-accent to-accent2 text-white font-medium text-sm hover:opacity-90 transition disabled:opacity-50 flex items-center gap-2"
                >
                  {saving && <Loader2 size={14} className="animate-spin" />}
                  {editingId ? 'Save Changes' : 'Add Client'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
