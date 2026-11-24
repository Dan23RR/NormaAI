'use client'

import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { useTranslations } from 'next-intl'
import { ImagePlus, Trash2 } from 'lucide-react'
import { Button, Dialog, Field, Input, Skeleton, Textarea, describedBy, useToast } from '@/components/ui'
import { ApiError } from '@/lib/api-error'
import type { User } from '@/lib/types'
import { SettingsSection } from './SettingsSection'
import {
  LIMITS,
  LOGO_TYPES,
  fetchLetterhead,
  fetchLogo,
  linesOf,
  logoProblem,
  removeLetterhead,
  removeLogo,
  saveLetterhead,
  textProblems,
  uploadLogo,
  type Letterhead,
  type LetterheadTexts,
} from './letterhead-api'

type Load = { status: 'loading' } | { status: 'error'; message: string } | { status: 'ready'; letterhead: Letterhead }

const EMPTY: LetterheadTexts = { name: '', address: '', contact: '', footer_note: '' }

const textsOf = (letterhead: Letterhead): LetterheadTexts => ({
  name: letterhead.name,
  address: letterhead.address ?? '',
  contact: letterhead.contact ?? '',
  footer_note: letterhead.footer_note ?? '',
})

const LIMIT_OF = {
  nameLong: LIMITS.name,
  addressLines: LIMITS.addressLines,
  addressLong: LIMITS.address,
  contactLong: LIMITS.contact,
  footerLong: LIMITS.footerNote,
} as const

/**
 * The top of the first page of a PDF and the foot of every page, as the client
 * will see them. On white whatever the theme: it is a sheet of paper.
 */
function Preview({ texts, logoUrl }: { texts: LetterheadTexts; logoUrl: string | null }) {
  const t = useTranslations('impostazioni.letterhead')
  const address = linesOf(texts.address)
  const contact = linesOf(texts.contact).join(' ')
  const note = linesOf(texts.footer_note).join(' ')
  return (
    <figure className="rounded-md border border-rule bg-white p-5 text-[#1b1f24] shadow-sm">
      <div aria-label={t('previewLabel')} role="group">
        <div className="flex items-start gap-4 border-b-2 border-[#1b1f24] pb-3">
          {logoUrl && <img src={logoUrl} alt={t('logoAlt')} className="max-h-14 max-w-[9rem] shrink-0 object-contain" />}
          <div className="min-w-0">
            <p className="break-words text-h4 font-semibold">{linesOf(texts.name).join(' ') || t('namePlaceholder')}</p>
            {address.map((line, index) => (
              <p key={index} className="break-words text-small text-[#4b5563]">
                {line}
              </p>
            ))}
            {contact && <p className="break-words text-small text-[#4b5563]">{contact}</p>}
          </div>
        </div>
        <div className="mt-6 border-t border-[#d0d5dd] pt-2 text-center text-[11px] leading-snug text-[#4b5563]">
          {note && <p className="break-words">{note}</p>}
          <p>{t('previewFoot')}</p>
        </div>
      </div>
      <figcaption className="mt-3 text-caption text-[#4b5563]">{t('previewCaption')}</figcaption>
    </figure>
  )
}

/**
 * The letterhead that heads the PDFs of the checks: everyone of the organisation
 * sees it, the admins change it (src/api/routers/letterhead.py).
 */
export function LetterheadSection({ user, demoMode }: { user: User; demoMode: boolean }) {
  const t = useTranslations('impostazioni.letterhead')
  const tu = useTranslations('ui')
  const { toast } = useToast()
  const isAdmin = user.role === 'admin'
  /** The server's own sentence when it says what is wrong (a 413, a 415, a 422), ours otherwise. */
  const failureText = useCallback(
    (err: unknown, key: string) => (err instanceof ApiError && err.detail ? err.detail : t(key)),
    [t],
  )

  const [load, setLoad] = useState<Load>({ status: 'loading' })
  const [texts, setTexts] = useState<LetterheadTexts>(EMPTY)
  const [submitted, setSubmitted] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [logoUrl, setLogoUrl] = useState<string | null>(null)
  const [logoBusy, setLogoBusy] = useState(false)
  const [logoError, setLogoError] = useState<string | null>(null)
  const [resetOpen, setResetOpen] = useState(false)
  const [resetting, setResetting] = useState(false)
  const [resetError, setResetError] = useState<string | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const shownUrl = useRef<string | null>(null)

  /** Show a logo (or none), letting go of the image shown before. */
  const showLogo = useCallback((blob: Blob | null) => {
    if (shownUrl.current) URL.revokeObjectURL(shownUrl.current)
    const url = blob && typeof URL.createObjectURL === 'function' ? URL.createObjectURL(blob) : null
    shownUrl.current = url
    setLogoUrl(url)
  }, [])

  useEffect(() => () => showLogo(null), [showLogo])

  const refreshLogo = useCallback(
    async (letterhead: Letterhead) => {
      if (!letterhead.logo) {
        showLogo(null)
        return
      }
      try {
        showLogo(await fetchLogo())
      } catch {
        showLogo(null) // the texts are what matters; the image is only a preview
      }
    },
    [showLogo],
  )

  const loadLetterhead = useCallback(async () => {
    setLoad({ status: 'loading' })
    try {
      const letterhead = await fetchLetterhead()
      setLoad({ status: 'ready', letterhead })
      setTexts(textsOf(letterhead))
      await refreshLogo(letterhead)
    } catch (err) {
      setLoad({ status: 'error', message: failureText(err, 'loadFailed') })
    }
  }, [failureText, refreshLogo])

  useEffect(() => {
    if (!demoMode) void loadLetterhead()
  }, [demoMode, loadLetterhead])

  if (demoMode) {
    return (
      <SettingsSection id="carta-intestata" title={t('title')} description={t('description')}>
        <p className="max-w-prose text-small text-ink-2">{t('demo')}</p>
      </SettingsSection>
    )
  }

  if (load.status !== 'ready') {
    return (
      <SettingsSection id="carta-intestata" title={t('title')} description={t('description')}>
        {load.status === 'loading' ? (
          <div className="space-y-3" role="status" aria-label={t('loading')}>
            <Skeleton className="h-28" label={t('loading')} />
            <Skeleton className="h-10 w-2/3" label={t('loading')} />
          </div>
        ) : (
          <div className="space-y-3">
            <p role="alert" className="text-small text-bad">
              {load.message}
            </p>
            <Button variant="secondary" size="sm" onClick={loadLetterhead}>
              {tu('retryLoad')}
            </Button>
          </div>
        )}
      </SettingsSection>
    )
  }

  const { letterhead } = load
  const problems = submitted ? textProblems(texts) : {}
  const problemText = (field: keyof LetterheadTexts) => {
    const problem = problems[field]
    if (!problem) return undefined
    return problem === 'nameMissing' ? t('problems.nameMissing') : t(`problems.${problem}`, { max: LIMIT_OF[problem] })
  }
  const set = (field: keyof LetterheadTexts) => (event: { target: { value: string } }) =>
    setTexts((current) => ({ ...current, [field]: event.target.value }))

  const save = async (event: FormEvent) => {
    event.preventDefault()
    setSubmitted(true)
    if (Object.keys(textProblems(texts)).length > 0) return
    setSaving(true)
    setSaveError(null)
    try {
      const saved = await saveLetterhead(texts)
      setLoad({ status: 'ready', letterhead: saved })
      setTexts(textsOf(saved))
      setSubmitted(false)
      toast({ kind: 'ok', title: t('savedTitle'), description: t('savedDescription') })
    } catch (err) {
      setSaveError(failureText(err, 'saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  const pickLogo = async (file: File | undefined) => {
    if (fileInput.current) fileInput.current.value = ''
    if (!file) return
    const problem = logoProblem(file)
    if (problem) {
      setLogoError(t(`problems.${problem}`))
      return
    }
    setLogoBusy(true)
    setLogoError(null)
    try {
      const saved = await uploadLogo(file)
      setLoad({ status: 'ready', letterhead: saved })
      await refreshLogo(saved)
      toast({ kind: 'ok', title: t('logoSavedTitle') })
    } catch (err) {
      setLogoError(failureText(err, 'logoFailed'))
    } finally {
      setLogoBusy(false)
    }
  }

  const dropLogo = async () => {
    setLogoBusy(true)
    setLogoError(null)
    try {
      const saved = await removeLogo()
      setLoad({ status: 'ready', letterhead: saved })
      showLogo(null)
      toast({ kind: 'ok', title: t('logoRemovedTitle') })
    } catch (err) {
      setLogoError(failureText(err, 'logoFailed'))
    } finally {
      setLogoBusy(false)
    }
  }

  const reset = async () => {
    setResetting(true)
    setResetError(null)
    try {
      await removeLetterhead()
      setResetOpen(false)
      toast({ kind: 'ok', title: t('resetDoneTitle') })
      await loadLetterhead()
    } catch (err) {
      setResetError(failureText(err, 'resetFailed'))
    } finally {
      setResetting(false)
    }
  }

  return (
    <SettingsSection id="carta-intestata" title={t('title')} description={t('description')}>
      <div className="space-y-6">
        <Preview texts={texts} logoUrl={logoUrl} />
        {!letterhead.configured && <p className="text-small text-ink-2">{t('notConfigured')}</p>}

        {!isAdmin ? (
          <p className="max-w-prose text-small text-ink-2">{t('adminOnly')}</p>
        ) : (
          <>
            <form onSubmit={save} noValidate className="space-y-4 rounded-lg border border-rule bg-surface p-5">
              <Field label={t('name')} htmlFor="letterhead-name" required help={t('nameHelp')} error={problemText('name')}>
                <Input
                  id="letterhead-name"
                  value={texts.name}
                  onChange={set('name')}
                  maxLength={LIMITS.name + 50}
                  autoComplete="organization"
                  invalid={!!problems.name}
                  aria-describedby={describedBy('letterhead-name', { help: t('nameHelp'), error: problemText('name') })}
                />
              </Field>
              <Field label={t('address')} htmlFor="letterhead-address" help={t('addressHelp')} error={problemText('address')}>
                <Textarea
                  id="letterhead-address"
                  value={texts.address}
                  onChange={set('address')}
                  rows={3}
                  autoComplete="street-address"
                  invalid={!!problems.address}
                  aria-describedby={describedBy('letterhead-address', { help: t('addressHelp'), error: problemText('address') })}
                />
              </Field>
              <Field label={t('contact')} htmlFor="letterhead-contact" help={t('contactHelp')} error={problemText('contact')}>
                <Input
                  id="letterhead-contact"
                  value={texts.contact}
                  onChange={set('contact')}
                  placeholder={t('contactPlaceholder')}
                  invalid={!!problems.contact}
                  aria-describedby={describedBy('letterhead-contact', { help: t('contactHelp'), error: problemText('contact') })}
                />
              </Field>
              <Field
                label={t('footerNote')}
                htmlFor="letterhead-footer"
                help={t('footerNoteHelp')}
                error={problemText('footer_note')}
              >
                <Input
                  id="letterhead-footer"
                  value={texts.footer_note}
                  onChange={set('footer_note')}
                  invalid={!!problems.footer_note}
                  aria-describedby={describedBy('letterhead-footer', { help: t('footerNoteHelp'), error: problemText('footer_note') })}
                />
              </Field>
              {saveError && (
                <p role="alert" className="text-small text-bad">
                  {saveError}
                </p>
              )}
              <Button type="submit" loading={saving}>
                {saving ? t('saving') : t('save')}
              </Button>
            </form>

            <div className="rounded-lg border border-rule bg-surface p-5">
              <h3 className="text-h4">{t('logoTitle')}</h3>
              <p className="mt-1 max-w-prose text-small text-ink-2">{t('logoLead')}</p>
              {!letterhead.logo && <p className="mt-2 text-small text-ink-3">{t('logoNone')}</p>}
              <div className="mt-4 flex flex-wrap gap-3">
                <input
                  ref={fileInput}
                  id="letterhead-logo"
                  type="file"
                  accept={LOGO_TYPES.join(',')}
                  className="sr-only"
                  aria-label={letterhead.logo ? t('logoReplace') : t('logoUpload')}
                  onChange={(event) => void pickLogo(event.target.files?.[0])}
                  disabled={logoBusy}
                />
                <Button
                  type="button"
                  variant="secondary"
                  loading={logoBusy}
                  onClick={() => fileInput.current?.click()}
                  iconLeft={<ImagePlus className="h-4 w-4" aria-hidden="true" />}
                >
                  {logoBusy ? t('logoUploading') : letterhead.logo ? t('logoReplace') : t('logoUpload')}
                </Button>
                {letterhead.logo && (
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={dropLogo}
                    disabled={logoBusy}
                    iconLeft={<Trash2 className="h-4 w-4" aria-hidden="true" />}
                  >
                    {t('logoRemove')}
                  </Button>
                )}
              </div>
              {logoError && (
                <p role="alert" className="mt-3 text-small text-bad">
                  {logoError}
                </p>
              )}
            </div>

            {letterhead.configured && (
              <div className="rounded-lg border border-rule bg-surface p-5">
                <h3 className="text-h4">{t('reset')}</h3>
                <p className="mt-1 max-w-prose text-small text-ink-2">{t('resetLead')}</p>
                <Button
                  className="mt-4"
                  variant="danger"
                  onClick={() => setResetOpen(true)}
                  iconLeft={<Trash2 className="h-4 w-4" aria-hidden="true" />}
                >
                  {t('reset')}
                </Button>
              </div>
            )}
          </>
        )}
      </div>

      <Dialog
        open={resetOpen}
        onClose={() => {
          if (!resetting) setResetOpen(false)
        }}
        title={t('resetTitle')}
        description={t('resetDescription')}
        footer={
          <>
            <Button variant="secondary" onClick={() => setResetOpen(false)} disabled={resetting}>
              {t('cancel')}
            </Button>
            <Button variant="danger" onClick={reset} loading={resetting}>
              {t('resetConfirm')}
            </Button>
          </>
        }
      >
        {resetError ? (
          <p role="alert" className="text-small text-bad">
            {resetError}
          </p>
        ) : null}
      </Dialog>
    </SettingsSection>
  )
}
