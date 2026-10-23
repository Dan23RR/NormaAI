'use client'

import { useRef, useState, type FormEvent } from 'react'
import { useFormatter, useTranslations } from 'next-intl'
import { FileText, Upload } from 'lucide-react'
import { Button, EmptyState, Field, FrameworkBadge, Select, TBody, TD, TH, THead, TR, Table, frameworkLabel, useToast } from '@/components/ui'
import { useErrorText } from '@/i18n/errors'
import { INT } from '@/i18n/format'
import { api } from '@/lib/api'
import { useAuth } from '@/hooks/useAuth'
import type { Client } from '@/lib/types'
import { FRAMEWORK_KEYS, isFrameworkKey } from './clients-api'
import { formatIsoDateTime } from './format'

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

/**
 * Upload of compliance documents against POST /api/v1/documents/upload.
 * The backend indexes them for the organization and does not keep a list,
 * so the table shows the uploads of this session only.
 */
export function DocumentsTab({ client }: { client: Client }) {
  const t = useTranslations('clienti.documents')
  const tRoot = useTranslations()
  const format = useFormatter()
  const errorText = useErrorText()
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

  const formatBytes = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${format.number(bytes / 1024, { maximumFractionDigits: 0 })} KB`
    return `${format.number(bytes / (1024 * 1024), { maximumFractionDigits: 1 })} MB`
  }

  if (demoMode) {
    return (
      <div className="space-y-4">
        <div className="rounded-lg border border-rule bg-surface p-5">
          <h3 className="text-h4">{t('demoTitle')}</h3>
          <p className="mt-2 max-w-prose text-body text-ink-2">{t('demoBody')}</p>
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
      setFileError(t('unsupported', { ext: ext || t('noExtension') }))
    } else if (picked.size === 0) {
      setFileError(t('emptyFile'))
    } else if (picked.size > MAX_BYTES) {
      setFileError(t('tooLarge', { size: formatBytes(picked.size) }))
    }
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!file) {
      setFileError(t('chooseFile'))
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
      toast({ kind: 'ok', title: t('processedTitle'), description: doc.filename })
      setFile(null)
      if (inputRef.current) inputRef.current.value = ''
    } catch (err) {
      setError(errorText(err, 'clienti.documents.failed'))
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="space-y-6">
      <form onSubmit={submit} className="rounded-lg border border-rule bg-surface p-5">
        <h3 className="text-h4">{t('uploadTitle')}</h3>
        <p className="mt-1 max-w-prose text-small text-ink-2">{t('uploadLead')}</p>
        <div className="mt-4 grid gap-4 md:grid-cols-[1fr_240px]">
          <Field label={t('file')} htmlFor="doc-file" required error={fileError ?? undefined}>
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
          <Field label={t('framework')} htmlFor="doc-framework" help={t('frameworkHelp')}>
            <Select
              id="doc-framework"
              value={framework}
              onChange={(e) => setFramework(e.target.value)}
              disabled={uploading}
              aria-describedby="doc-framework-help"
            >
              <option value="">{t('noFramework')}</option>
              {FRAMEWORK_KEYS.map((key) => (
                <option key={key} value={key}>
                  {frameworkLabel(key, tRoot)}
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
            {uploading ? t('processing') : t('upload')}
          </Button>
          {uploading && (
            <p role="status" className="text-small text-ink-2">
              {t('progress', { name: file?.name ?? '' })}
            </p>
          )}
        </div>
      </form>

      {uploads.length === 0 ? (
        <EmptyState
          icon={<FileText className="h-8 w-8" aria-hidden="true" />}
          title={t('emptyTitle')}
          description={t('emptyDescription')}
        />
      ) : (
        <section aria-labelledby="uploads-title">
          <h3 id="uploads-title" className="mb-3 text-h4">
            {t('sessionTitle')}
          </h3>
          <Table>
            <THead>
              <TR>
                <TH>{t('colFile')}</TH>
                <TH>{t('colFramework')}</TH>
                <TH numeric className="hidden sm:table-cell">
                  {t('colChunks')}
                </TH>
                <TH numeric className="hidden sm:table-cell">
                  {t('colSize')}
                </TH>
                <TH>{t('colUploaded')}</TH>
              </TR>
            </THead>
            <TBody>
              {uploads.map((doc) => (
                <TR key={doc.id}>
                  <TD className="font-medium">{doc.filename}</TD>
                  <TD>{doc.framework ? <FrameworkBadge framework={doc.framework} /> : <span className="text-ink-3">{t('none')}</span>}</TD>
                  <TD numeric className="hidden sm:table-cell">
                    {doc.chunksIndexed === null ? <span className="text-ink-3">{tRoot('ui.notAvailable')}</span> : format.number(doc.chunksIndexed, INT)}
                  </TD>
                  <TD numeric className="hidden sm:table-cell">
                    {formatBytes(doc.sizeBytes)}
                  </TD>
                  <TD className="tabular text-ink-2">{formatIsoDateTime(doc.uploadedAt)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <p className="mt-2 text-caption text-ink-3">{t('deleteNote')}</p>
        </section>
      )}
    </div>
  )
}
