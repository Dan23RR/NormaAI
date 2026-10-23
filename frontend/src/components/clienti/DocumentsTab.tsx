'use client'

import { useRef, useState, type FormEvent } from 'react'
import { FileText, Upload } from 'lucide-react'
import { Button, EmptyState, Field, FrameworkBadge, Select, TBody, TD, TH, THead, TR, Table, frameworkLabel, useToast } from '@/components/ui'
import { api } from '@/lib/api'
import { useAuth } from '@/hooks/useAuth'
import type { Client } from '@/lib/types'
import { FRAMEWORK_KEYS, isFrameworkKey } from './clients-api'
import { formatInt, formatIsoDateTime } from './format'

/** Mirrors the allowed extensions and the 50 MB limit in src/api/routers/data.py. */
const ALLOWED_EXTENSIONS = ['.pdf', '.html', '.htm', '.png', '.jpg', '.jpeg', '.tiff', '.tif', '.bmp']
const MAX_BYTES = 50 * 1024 * 1024

interface UploadResponse {
  status: string
  message?: string
  data?: { filename?: string; size_bytes?: number; chunks_indexed?: number; framework?: string | null }
}

interface UploadedDocument {
  id: string
  filename: string
  sizeBytes: number
  chunksIndexed: number | null
  framework: string | null
  uploadedAt: string
}

function extensionOf(name: string): string {
  const idx = name.lastIndexOf('.')
  return idx >= 0 ? name.slice(idx).toLowerCase() : ''
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1).replace('.', ',')} MB`
}

/**
 * Upload of compliance documents against POST /api/v1/documents/upload.
 * The backend indexes them for the organization and does not keep a list,
 * so the table shows the uploads of this session only.
 */
export function DocumentsTab({ client }: { client: Client }) {
  const { demoMode } = useAuth()
  const { toast } = useToast()
  const inputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [framework, setFramework] = useState<string>(() => {
    const first = (client.applicable_frameworks ?? []).find(isFrameworkKey)
    return first ?? ''
  })
  const [fileError, setFileError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [uploads, setUploads] = useState<UploadedDocument[]>([])

  if (demoMode) {
    return (
      <div className="space-y-4">
        <div className="rounded-lg border border-rule bg-surface p-5">
          <h3 className="text-h4">Nella demo il caricamento non è disponibile</h3>
          <p className="mt-2 max-w-prose text-body text-ink-2">
            L&apos;elaborazione dei documenti (estrazione del testo, suddivisione per articoli, indicizzazione) gira sul
            server e non viene simulata con dati di esempio. Con un account reale puoi caricare PDF, HTML e immagini
            fino a 50 MB.
          </p>
        </div>
      </div>
    )
  }

  const onPick = (picked: File | null) => {
    setFile(picked)
    setFileError(null)
    if (!picked) return
    const ext = extensionOf(picked.name)
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      setFileError(`Formato non supportato (${ext || 'senza estensione'}). Formati accettati: PDF, HTML, PNG, JPEG, TIFF, BMP.`)
    } else if (picked.size === 0) {
      setFileError('Il file è vuoto.')
    } else if (picked.size > MAX_BYTES) {
      setFileError(`Il file pesa ${formatBytes(picked.size)}: il limite è 50 MB.`)
    }
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!file) {
      setFileError('Scegli un file da caricare.')
      return
    }
    if (fileError) return
    setUploading(true)
    setError(null)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const query = framework ? `?framework=${encodeURIComponent(framework)}` : ''
      const res = await api.upload<UploadResponse>(`/api/v1/documents/upload${query}`, formData)
      const doc: UploadedDocument = {
        id: `${Date.now()}-${file.name}`,
        filename: res.data?.filename ?? file.name,
        sizeBytes: res.data?.size_bytes ?? file.size,
        chunksIndexed: typeof res.data?.chunks_indexed === 'number' ? res.data.chunks_indexed : null,
        framework: res.data?.framework ?? (framework || null),
        uploadedAt: new Date().toISOString(),
      }
      setUploads((prev) => [doc, ...prev])
      toast({ kind: 'ok', title: 'Documento elaborato', description: doc.filename })
      setFile(null)
      if (inputRef.current) inputRef.current.value = ''
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Caricamento non riuscito. Riprova.')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="space-y-6">
      <form onSubmit={submit} className="rounded-lg border border-rule bg-surface p-5">
        <h3 className="text-h4">Carica un documento</h3>
        <p className="mt-1 max-w-prose text-small text-ink-2">
          Politiche, procedure, report: il testo viene estratto, suddiviso per articoli e indicizzato per la tua
          organizzazione (non per il singolo cliente). PDF, HTML, PNG, JPEG, TIFF o BMP fino a 50 MB.
        </p>
        <div className="mt-4 grid gap-4 md:grid-cols-[1fr_240px]">
          <Field label="File" htmlFor="doc-file" required error={fileError ?? undefined}>
            <input
              ref={inputRef}
              id="doc-file"
              type="file"
              accept={ALLOWED_EXTENSIONS.join(',')}
              onChange={(e) => onPick(e.target.files?.[0] ?? null)}
              disabled={uploading}
              aria-invalid={fileError ? true : undefined}
              aria-describedby={fileError ? 'doc-file-error' : undefined}
              className="block w-full rounded-md border border-rule-2 bg-surface px-3 py-2 text-body text-ink file:mr-3 file:rounded-md file:border-0 file:bg-surface-3 file:px-3 file:py-1 file:text-small file:font-medium file:text-ink focus:border-union focus:outline-none focus:ring-2 focus:ring-union/20"
            />
          </Field>
          <Field label="Framework" htmlFor="doc-framework" help="Facoltativo: aiuta l’indicizzazione.">
            <Select
              id="doc-framework"
              value={framework}
              onChange={(e) => setFramework(e.target.value)}
              disabled={uploading}
              aria-describedby="doc-framework-help"
            >
              <option value="">Nessuno in particolare</option>
              {FRAMEWORK_KEYS.map((key) => (
                <option key={key} value={key}>
                  {frameworkLabel(key)}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        {error && (
          <p role="alert" className="mt-4 rounded-md border border-bad/30 bg-bad/10 px-3 py-2 text-small text-bad">
            {error}
          </p>
        )}
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button type="submit" loading={uploading} iconLeft={<Upload className="h-4 w-4" aria-hidden="true" />}>
            {uploading ? 'Elaborazione in corso' : 'Carica il documento'}
          </Button>
          {uploading && (
            <p role="status" className="text-small text-ink-2">
              Estrazione e indicizzazione di {file?.name}: può richiedere qualche minuto per i PDF lunghi.
            </p>
          )}
        </div>
      </form>

      {uploads.length === 0 ? (
        <EmptyState
          icon={<FileText className="h-8 w-8" aria-hidden="true" />}
          title="Nessun documento caricato in questa sessione"
          description="Il server non espone ancora l’elenco dei documenti indicizzati: qui compaiono i caricamenti fatti ora."
        />
      ) : (
        <section aria-labelledby="uploads-title">
          <h3 id="uploads-title" className="mb-3 text-h4">
            Caricati in questa sessione
          </h3>
          <Table>
            <THead>
              <TR>
                <TH>File</TH>
                <TH>Framework</TH>
                <TH numeric className="hidden sm:table-cell">
                  Blocchi indicizzati
                </TH>
                <TH numeric className="hidden sm:table-cell">
                  Dimensione
                </TH>
                <TH>Caricato</TH>
              </TR>
            </THead>
            <TBody>
              {uploads.map((doc) => (
                <TR key={doc.id}>
                  <TD className="font-medium">{doc.filename}</TD>
                  <TD>{doc.framework ? <FrameworkBadge framework={doc.framework} /> : <span className="text-ink-3">Nessuno</span>}</TD>
                  <TD numeric className="hidden sm:table-cell">
                    {doc.chunksIndexed === null ? <span className="text-ink-3">n.d.</span> : formatInt(doc.chunksIndexed)}
                  </TD>
                  <TD numeric className="hidden sm:table-cell">
                    {formatBytes(doc.sizeBytes)}
                  </TD>
                  <TD className="tabular text-ink-2">{formatIsoDateTime(doc.uploadedAt)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <p className="mt-2 text-caption text-ink-3">
            La cancellazione di un documento indicizzato non è ancora disponibile dal server: scrivi a info@normaai.org
            per farlo rimuovere.
          </p>
        </section>
      )}
    </div>
  )
}
