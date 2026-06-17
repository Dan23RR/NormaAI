'use client'

import { useState, useCallback, useRef, useEffect } from 'react'
import { api } from '@/lib/api'
import { isDemoMode } from '@/lib/auth'
import type { Framework } from '@/lib/types'
import { FRAMEWORKS } from '@/lib/types'
import { Upload, FileText, CheckCircle, XCircle, Loader2, File, AlertTriangle } from 'lucide-react'

const ALLOWED_TYPES = [
  'application/pdf',
  'text/html',
  'image/png',
  'image/jpeg',
  'image/tiff',
]

const ALLOWED_EXTENSIONS = ['.pdf', '.html', '.htm', '.png', '.jpg', '.jpeg', '.tiff', '.tif']

interface UploadedDocument {
  id: string
  filename: string
  status: 'uploading' | 'processing' | 'completed' | 'failed'
  progress: number
  error?: string
  framework?: string
  uploaded_at: string
}

interface Processor {
  id: string
  name: string
  description?: string
}

function getFileExtension(name: string): string {
  const idx = name.lastIndexOf('.')
  return idx >= 0 ? name.slice(idx).toLowerCase() : ''
}

function isAllowedFile(file: File): boolean {
  if (ALLOWED_TYPES.includes(file.type)) return true
  return ALLOWED_EXTENSIONS.includes(getFileExtension(file.name))
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const STATUS_CONFIG = {
  uploading: { label: 'Uploading', color: 'text-blue-400', bg: 'bg-blue-400/10', icon: Loader2 },
  processing: { label: 'Processing', color: 'text-yellow-400', bg: 'bg-yellow-400/10', icon: Loader2 },
  completed: { label: 'Completed', color: 'text-green-400', bg: 'bg-green-400/10', icon: CheckCircle },
  failed: { label: 'Failed', color: 'text-red-400', bg: 'bg-red-400/10', icon: XCircle },
}

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<UploadedDocument[]>([])
  const [framework, setFramework] = useState<Framework | ''>('')
  const [processors, setProcessors] = useState<Processor[]>([])
  const [dragActive, setDragActive] = useState(false)
  const [error, setError] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Load available processors on mount
  useEffect(() => {
    api.get<Processor[]>('/api/v1/processors')
      .then(setProcessors)
      .catch(() => { /* processors are optional */ })
  }, [])

  const uploadFile = useCallback(async (file: File) => {
    if (!isAllowedFile(file)) {
      setError(`File type not allowed: ${file.name}. Accepted: PDF, HTML, PNG, JPEG, TIFF`)
      return
    }

    const tempId = crypto.randomUUID()
    const doc: UploadedDocument = {
      id: tempId,
      filename: file.name,
      status: 'uploading',
      progress: 0,
      framework: framework || undefined,
      uploaded_at: new Date().toISOString(),
    }

    setDocuments(prev => [doc, ...prev])
    setError('')

    try {
      // Demo mode: simulate upload
      if (isDemoMode()) {
        for (let p = 10; p <= 90; p += 20) {
          await new Promise(r => setTimeout(r, 200))
          setDocuments(prev => prev.map(d =>
            d.id === tempId ? { ...d, progress: p } : d
          ))
        }
        await new Promise(r => setTimeout(r, 300))
        setDocuments(prev => prev.map(d =>
          d.id === tempId ? { ...d, status: 'processing', progress: 100 } : d
        ))
        await new Promise(r => setTimeout(r, 1500))
        setDocuments(prev => prev.map(d =>
          d.id === tempId ? { ...d, status: 'completed' } : d
        ))
        return
      }

      const formData = new FormData()
      formData.append('file', file)
      if (framework) formData.append('framework', framework)

      const data = await api.upload<{ id?: string }>('/api/v1/documents/upload', formData)
      setDocuments(prev => prev.map(d =>
        d.id === tempId
          ? { ...d, id: data.id || tempId, status: 'processing', progress: 100 }
          : d
      ))

      // Poll for completion (simple approach)
      setTimeout(() => {
        setDocuments(prev => prev.map(d =>
          d.id === (data.id || tempId) ? { ...d, status: 'completed' } : d
        ))
      }, 3000)
    } catch (err: unknown) {
      setDocuments(prev => prev.map(d =>
        d.id === tempId
          ? { ...d, status: 'failed', error: err instanceof Error ? err.message : 'Upload failed' }
          : d
      ))
    }
  }, [framework])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragActive(false)
    const files = Array.from(e.dataTransfer.files)
    files.forEach(uploadFile)
  }, [uploadFile])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragActive(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragActive(false)
  }, [])

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    files.forEach(uploadFile)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }, [uploadFile])

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Framework selector */}
      <div>
        <label htmlFor="doc-framework" className="block text-xs text-slate-500 mb-1.5 uppercase tracking-wider">
          Framework (optional)
        </label>
        <select
          id="doc-framework"
          value={framework}
          onChange={(e) => setFramework(e.target.value as Framework | '')}
          className="w-full sm:w-72 px-3 py-2.5 bg-surface border border-white/[0.06] rounded-lg text-white focus:outline-none focus:border-accent/40"
        >
          <option value="">No specific framework</option>
          {FRAMEWORKS.map(fw => (
            <option key={fw.value} value={fw.value}>{fw.label}</option>
          ))}
        </select>
      </div>

      {/* Drop zone */}
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => fileInputRef.current?.click()}
        className={`relative flex flex-col items-center justify-center py-16 px-6 rounded-xl border-2 border-dashed cursor-pointer transition-all ${
          dragActive
            ? 'border-accent/60 bg-accent/5'
            : 'border-white/[0.08] bg-surface hover:border-white/[0.15] hover:bg-surface2'
        }`}
      >
        <Upload size={36} className={`mb-3 ${dragActive ? 'text-accent' : 'text-slate-500'}`} />
        <p className="text-sm font-medium text-slate-300">
          {dragActive ? 'Drop files here' : 'Drag & drop files or click to browse'}
        </p>
        <p className="text-xs text-slate-500 mt-1.5">
          PDF, HTML, PNG, JPEG, TIFF
        </p>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept={ALLOWED_EXTENSIONS.join(',')}
          onChange={handleFileSelect}
          className="hidden"
        />
      </div>

      {/* Error */}
      {error && (
        <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm flex items-center gap-2">
          <AlertTriangle size={16} /> {error}
        </div>
      )}

      {/* Available processors */}
      {processors.length > 0 && (
        <div className="bg-surface border border-white/[0.06] rounded-xl p-5">
          <h3 className="text-xs uppercase tracking-widest text-slate-500 font-semibold mb-3">Available Processors</h3>
          <div className="flex flex-wrap gap-2">
            {processors.map(p => (
              <span key={p.id} className="text-xs px-2.5 py-1 bg-accent/10 text-accent rounded-lg border border-accent/20">
                {p.name}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Document list */}
      {documents.length > 0 && (
        <div className="bg-surface border border-white/[0.06] rounded-xl p-5">
          <h3 className="text-xs uppercase tracking-widest text-slate-500 font-semibold mb-4">
            Uploaded Documents
          </h3>
          <div className="space-y-3">
            {documents.map(doc => {
              const cfg = STATUS_CONFIG[doc.status]
              const StatusIcon = cfg.icon
              const isAnimated = doc.status === 'uploading' || doc.status === 'processing'

              return (
                <div key={doc.id} className="flex items-center gap-3 p-3 bg-surface2 rounded-lg border border-white/[0.04]">
                  <File size={18} className="text-slate-400 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-white truncate">{doc.filename}</span>
                      {doc.framework && (
                        <span className="text-[10px] px-1.5 py-0.5 bg-accent/10 text-accent rounded shrink-0">
                          {doc.framework}
                        </span>
                      )}
                    </div>
                    {/* Progress bar */}
                    {doc.status === 'uploading' && (
                      <div className="w-full h-1.5 bg-surface rounded-full mt-1.5 overflow-hidden">
                        <div
                          className="h-full bg-accent rounded-full transition-all duration-300"
                          style={{ width: `${doc.progress}%` }}
                        />
                      </div>
                    )}
                    {doc.error && (
                      <p className="text-xs text-red-400 mt-0.5">{doc.error}</p>
                    )}
                  </div>
                  <span className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg ${cfg.bg} ${cfg.color} shrink-0`}>
                    <StatusIcon size={12} className={isAnimated ? 'animate-spin' : ''} />
                    {cfg.label}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Empty state */}
      {documents.length === 0 && (
        <div className="flex flex-col items-center justify-center py-12 text-slate-500">
          <FileText size={40} className="mb-3 text-slate-600" />
          <p className="text-sm">No documents uploaded yet</p>
          <p className="text-xs mt-1">Upload regulatory documents for analysis</p>
        </div>
      )}

      {/* AI disclosure */}
      <p className="text-[9px] text-slate-600 italic mt-4">
        L&apos;analisi documentale è assistita da AI (AI Act Art. 50, Reg. UE 2024/1689) - verificare i risultati con consulenti qualificati.
      </p>
    </div>
  )
}
