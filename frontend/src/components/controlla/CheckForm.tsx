'use client'

import { useRef, useState, type DragEvent, type FormEvent } from 'react'
import { useFormatter, useTranslations } from 'next-intl'
import { FileText, FileUp, Info, X } from 'lucide-react'
import { Button, buttonClasses } from '@/components/ui/Button'
import { Checkbox, Field, Input, Select, Textarea, describedBy } from '@/components/ui/Field'
import { Tabs } from '@/components/ui/Tabs'
import { cn } from '@/lib/cn'
import type { Client } from '@/lib/types'
import { ACCEPTED_EXTENSIONS, MAX_FILE_BYTES, checkFile, checkText, extensionOf } from './documents-api'
import { describeFailure, type Failure } from './errors'
import { FailureMessage } from './FailureMessage'
import type { DocumentCheck } from './types'

type Mode = 'file' | 'text'

/** Today as YYYY-MM-DD in the person's own time zone: the latest date a document can bear. */
function todayIso(): string {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

/**
 * The start of a check: a file (chosen or dropped) or a pasted text, the
 * client and the date of the document when the person has them, and whether
 * to keep watching the provisions it cites.
 */
export function CheckForm({
  clients,
  clientsFailed,
  initialClientId,
  demo,
  onChecked,
}: {
  clients: Client[]
  /** True when the list of clients could not be loaded: the check still works, without one. */
  clientsFailed?: boolean
  initialClientId?: string
  demo: boolean
  onChecked: (check: DocumentCheck) => void
}) {
  const t = useTranslations('controlla.form')
  const td = useTranslations('controlla.demo')
  const ts = useTranslations('controlla.storage')
  const format = useFormatter()
  const inputRef = useRef<HTMLInputElement>(null)

  const [mode, setMode] = useState<Mode>('file')
  const [file, setFile] = useState<File | null>(null)
  const [fileError, setFileError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const [text, setText] = useState('')
  const [textError, setTextError] = useState<string | null>(null)
  const [name, setName] = useState('')
  // Null until the person chooses: the client of the link that led here stays selected
  // even when the list of clients arrives after the form.
  const [clientChoice, setClientChoice] = useState<string | null>(null)
  const [date, setDate] = useState('')
  const [dateError, setDateError] = useState<string | null>(null)
  const [watch, setWatch] = useState(true)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<Failure | null>(null)

  // A client that is not in the list (a stale link) is neither shown nor sent.
  const wanted = clientChoice ?? initialClientId ?? ''
  const clientId = clients.some((c) => c.id === wanted) ? wanted : ''

  // `roundUp` for a file over the limit: 10 MB and one byte must not read as "10 MB".
  const formatBytes = (bytes: number, roundUp = false): string => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${format.number(bytes / 1024, { maximumFractionDigits: 0 })} KB`
    const megabytes = bytes / (1024 * 1024)
    return `${format.number(roundUp ? Math.ceil(megabytes * 10) / 10 : megabytes, { maximumFractionDigits: 1 })} MB`
  }

  const pick = (picked: File | null) => {
    setFile(picked)
    setFailure(null)
    setFileError(null)
    if (!picked) return
    const extension = extensionOf(picked.name)
    if (!(ACCEPTED_EXTENSIONS as readonly string[]).includes(extension)) {
      setFileError(t('errors.unsupported', { ext: extension || t('errors.noExtension') }))
    } else if (picked.size === 0) {
      setFileError(t('errors.emptyFile'))
    } else if (picked.size > MAX_FILE_BYTES) {
      setFileError(t('errors.tooLarge', { size: formatBytes(picked.size, true) }))
    }
  }

  const clearFile = () => {
    pick(null)
    if (inputRef.current) inputRef.current.value = ''
  }

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setDragging(false)
    if (busy) return
    pick(event.dataTransfer?.files?.[0] ?? null)
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (busy) return
    let valid = true
    if (mode === 'file') {
      if (!file) {
        setFileError(t('errors.chooseFile'))
        valid = false
      } else if (fileError) {
        valid = false
      }
    } else if (!text.trim()) {
      setTextError(t('errors.textRequired'))
      valid = false
    }
    if (date && date > todayIso()) {
      setDateError(t('errors.dateFuture'))
      valid = false
    }
    if (!valid) return

    const options = {
      clientId: clientId || null,
      documentDate: date || null,
      watch,
    }
    setBusy(true)
    setFailure(null)
    try {
      const check =
        mode === 'file' && file ? await checkFile(file, options) : await checkText(text, name.trim() || t('pastedName'), options)
      onChecked(check)
    } catch (err) {
      setFailure(describeFailure(err))
    } finally {
      setBusy(false)
    }
  }

  const modes = [
    { id: 'file', label: t('modeFile') },
    { id: 'text', label: t('modeText') },
  ]
  const dateHelp = t('dateHelp')
  const clientHelp = clientsFailed ? t('clientsUnavailable') : t('clientHelp')

  return (
    <form onSubmit={submit} noValidate aria-labelledby="check-form-title" className="min-w-0 rounded-lg border border-rule bg-surface p-5">
      <h2 id="check-form-title" className="text-h3">
        {t('title')}
      </h2>
      <p className="mt-1 max-w-prose text-small text-ink-2">{t('lead')}</p>

      {demo && (
        <p className="mt-4 flex items-start gap-2 rounded-md border border-rule bg-surface-2 px-3 py-2 text-small text-ink-2">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-union" aria-hidden="true" />
          <span>{td('form')}</span>
        </p>
      )}

      <Tabs tabs={modes} value={mode} onChange={(id) => setMode(id === 'text' ? 'text' : 'file')} label={t('modeLabel')} className="mt-4" />

      {mode === 'file' ? (
        <div role="tabpanel" aria-label={t('modeFile')} className="mt-4">
          <p id="check-file-label" className="text-small font-medium text-ink">
            {t('fileLabel')}
          </p>
          <div
            role="group"
            aria-labelledby="check-file-label"
            onDragOver={(event) => {
              event.preventDefault()
              if (!busy) setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            className={cn(
              'mt-1.5 flex flex-col items-center gap-2 rounded-lg border-2 border-dashed px-4 py-6 text-center transition-colors',
              dragging ? 'border-union bg-union/5' : fileError ? 'border-bad/50 bg-surface-2' : 'border-rule-2 bg-surface-2',
            )}
          >
            <FileUp className="h-6 w-6 text-ink-2" aria-hidden="true" />
            <p className="text-body text-ink">{t('drop')}</p>
            <input
              ref={inputRef}
              id="check-file"
              type="file"
              accept={ACCEPTED_EXTENSIONS.join(',')}
              onChange={(event) => pick(event.target.files?.[0] ?? null)}
              disabled={busy}
              aria-invalid={fileError ? true : undefined}
              aria-describedby={fileError ? 'check-file-error check-file-help' : 'check-file-help'}
              className="peer sr-only"
            />
            <label
              htmlFor="check-file"
              className={cn(
                buttonClasses({ variant: 'secondary' }),
                'cursor-pointer peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-union',
                busy && 'pointer-events-none opacity-50',
              )}
            >
              {t('choose')}
            </label>
            <p id="check-file-help" className="text-caption text-ink-2">
              {t('formats')}
            </p>
          </div>
          {file && (
            <p className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-small text-ink" aria-live="polite">
              <FileText className="h-4 w-4 shrink-0 text-ink-2" aria-hidden="true" />
              <span className="min-w-0 break-all">{t('selected', { name: file.name, size: formatBytes(file.size) })}</span>
              <Button type="button" variant="ghost" size="sm" onClick={clearFile} disabled={busy} iconLeft={<X className="h-3.5 w-3.5" aria-hidden="true" />}>
                {t('remove')}
              </Button>
            </p>
          )}
          {fileError && (
            <p id="check-file-error" role="alert" className="mt-2 text-caption text-bad">
              {fileError}
            </p>
          )}
        </div>
      ) : (
        <div role="tabpanel" aria-label={t('modeText')} className="mt-4 space-y-4">
          <Field label={t('textLabel')} htmlFor="check-text" required error={textError ?? undefined}>
            <Textarea
              id="check-text"
              value={text}
              onChange={(event) => {
                setText(event.target.value)
                setTextError(null)
              }}
              rows={8}
              disabled={busy}
              placeholder={t('textPlaceholder')}
              invalid={!!textError}
              aria-describedby={describedBy('check-text', { error: textError ?? undefined })}
              className="min-h-[180px]"
            />
          </Field>
          <Field label={t('nameLabel')} htmlFor="check-name" help={t('nameHelp')}>
            <Input
              id="check-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              disabled={busy}
              maxLength={200}
              placeholder={t('namePlaceholder')}
              aria-describedby="check-name-help"
            />
          </Field>
        </div>
      )}

      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <Field label={t('client')} htmlFor="check-client" help={clientHelp}>
          <Select
            id="check-client"
            value={clientId}
            onChange={(event) => setClientChoice(event.target.value)}
            disabled={busy}
            aria-describedby="check-client-help"
          >
            <option value="">{t('clientNone')}</option>
            {clients.map((client) => (
              <option key={client.id} value={client.id}>
                {client.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label={t('date')} htmlFor="check-date" help={dateHelp} error={dateError ?? undefined}>
          <Input
            id="check-date"
            type="date"
            value={date}
            max={todayIso()}
            onChange={(event) => {
              setDate(event.target.value)
              setDateError(null)
            }}
            disabled={busy}
            invalid={!!dateError}
            aria-describedby={describedBy('check-date', { help: dateHelp, error: dateError ?? undefined })}
          />
        </Field>
      </div>

      <Checkbox
        id="check-watch"
        className="mt-5"
        checked={watch}
        onChange={(event) => setWatch(event.target.checked)}
        disabled={busy}
        label={t('watch')}
        description={t('watchHelp')}
      />

      {failure && <FailureMessage failure={failure} title={t('failedTitle')} className="mt-5" />}

      <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-2">
        <Button type="submit" loading={busy}>
          {busy ? t('submitting') : t('submit')}
        </Button>
        <div className="min-w-0 flex-1 basis-56 text-caption text-ink-2">
          {/* Always in the page, so that the progress is announced when it appears. */}
          <p role="status">{busy ? t('progress') : ''}</p>
          {!busy && <p>{ts('short')}</p>}
        </div>
      </div>
    </form>
  )
}
