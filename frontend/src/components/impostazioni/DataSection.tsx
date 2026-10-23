'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { Download, Mail, Trash2 } from 'lucide-react'
import { Button, Dialog, Field, Input, buttonClasses, useToast } from '@/components/ui'
import { useErrorText } from '@/i18n/errors'
import { api } from '@/lib/api'
import { getAccessToken } from '@/lib/auth'
import type { User } from '@/lib/types'
import { formatIsoDate } from '@/components/clienti/format'
import { SettingsSection } from './SettingsSection'

/**
 * GDPR rights against src/api/routers/gdpr.py (both admin-only):
 * - GET  /api/v1/gdpr/export           -> JSON dump of the organization's data (3 per hour)
 * - POST /api/v1/gdpr/erase {confirm_org_id} -> deletes the organization's content, keeps users and org
 * Account closure has no endpoint yet: it goes by email.
 */

interface EraseResponse {
  status: string
  org_id: string
  deleted: Record<string, number>
}

/** The organization id is a claim of the access token (src/auth/security.py). */
function orgIdFromToken(): string | null {
  const token = getAccessToken()
  if (!token) return null
  try {
    const segment = token.split('.')[1] ?? ''
    const base64 = segment.replace(/-/g, '+').replace(/_/g, '/')
    const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4)
    const payload = JSON.parse(atob(padded)) as { org_id?: unknown }
    return typeof payload.org_id === 'string' ? payload.org_id : null
  } catch {
    return null
  }
}

const DELETED_KEYS = ['clients', 'conversations', 'assessments', 'alerts']

export function DataSection({ user, demoMode }: { user: User; demoMode: boolean }) {
  const t = useTranslations('impostazioni.data')
  const errorText = useErrorText()
  const { toast } = useToast()
  const isAdmin = user.role === 'admin'
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)
  const [eraseOpen, setEraseOpen] = useState(false)
  const [confirmName, setConfirmName] = useState('')
  const [erasing, setErasing] = useState(false)
  const [eraseError, setEraseError] = useState<string | null>(null)

  const exportData = async () => {
    setExporting(true)
    setExportError(null)
    try {
      const data = await api.get<unknown>('/api/v1/gdpr/export')
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const filename = `normaai-export-${formatIsoDate(new Date().toISOString())}.json`
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      toast({ kind: 'ok', title: t('exportedTitle'), description: filename })
    } catch (err) {
      setExportError(errorText(err, 'impostazioni.data.exportFailed'))
    } finally {
      setExporting(false)
    }
  }

  const orgId = orgIdFromToken()
  const nameMatches = confirmName.trim().toLowerCase() === (user.organization_name ?? '').trim().toLowerCase()

  const erase = async () => {
    if (!orgId) return
    setErasing(true)
    setEraseError(null)
    try {
      const res = await api.post<EraseResponse>('/api/v1/gdpr/erase', { confirm_org_id: orgId })
      const parts = Object.entries(res.deleted ?? {}).map(([k, v]) => `${v} ${DELETED_KEYS.includes(k) ? t(`deleted.${k}`) : k}`)
      toast({ kind: 'ok', title: t('erasedTitle'), description: parts.join(', ') })
      setEraseOpen(false)
      setConfirmName('')
    } catch (err) {
      setEraseError(errorText(err, 'impostazioni.data.eraseFailed'))
    } finally {
      setErasing(false)
    }
  }

  const mailBody = user.organization_name
    ? t('mailBodyOrg', { email: user.email, org: user.organization_name })
    : t('mailBody', { email: user.email })
  const mailto = `mailto:info@normaai.org?subject=${encodeURIComponent(t('mailSubject'))}&body=${encodeURIComponent(mailBody)}`

  return (
    <SettingsSection id="dati" title={t('title')} description={t('description')}>
      <div className="space-y-6">
        <div className="rounded-lg border border-rule bg-surface p-5">
          <h3 className="text-h4">{t('exportTitle')}</h3>
          <p className="mt-1 max-w-prose text-small text-ink-2">{t('exportLead')}</p>
          {demoMode ? (
            <p className="mt-3 text-small text-ink-2">{t('exportDemo')}</p>
          ) : !isAdmin ? (
            <p className="mt-3 text-small text-ink-2">{t('exportAdminOnly')}</p>
          ) : (
            <>
              <Button
                className="mt-4"
                variant="secondary"
                onClick={exportData}
                loading={exporting}
                iconLeft={<Download className="h-4 w-4" aria-hidden="true" />}
              >
                {exporting ? t('exporting') : t('export')}
              </Button>
              {exportError && (
                <p role="alert" className="mt-3 text-small text-bad">
                  {exportError}
                </p>
              )}
            </>
          )}
        </div>

        {isAdmin && !demoMode && (
          <div className="rounded-lg border border-rule bg-surface p-5">
            <h3 className="text-h4">{t('eraseTitle')}</h3>
            <p className="mt-1 max-w-prose text-small text-ink-2">{t('eraseLead')}</p>
            {orgId ? (
              <Button
                className="mt-4"
                variant="danger"
                onClick={() => setEraseOpen(true)}
                iconLeft={<Trash2 className="h-4 w-4" aria-hidden="true" />}
              >
                {t('erase')}
              </Button>
            ) : (
              <p className="mt-3 text-small text-ink-2">{t('noOrgId')}</p>
            )}
          </div>
        )}

        <div className="rounded-lg border border-rule bg-surface p-5">
          <h3 className="text-h4">{t('accountTitle')}</h3>
          <p className="mt-1 max-w-prose text-small text-ink-2">{t('accountLead')}</p>
          <a href={mailto} className={buttonClasses({ variant: 'secondary', className: 'mt-4' })}>
            <Mail className="h-4 w-4" aria-hidden="true" />
            {t('accountMail')}
          </a>
        </div>
      </div>

      <Dialog
        open={eraseOpen}
        onClose={() => {
          if (!erasing) setEraseOpen(false)
        }}
        title={t('dialogTitle')}
        description={t('dialogDescription')}
        footer={
          <>
            <Button variant="secondary" onClick={() => setEraseOpen(false)} disabled={erasing}>
              {t('cancel')}
            </Button>
            <Button variant="danger" onClick={erase} loading={erasing} disabled={!nameMatches}>
              {t('erase')}
            </Button>
          </>
        }
      >
        <Field label={t('confirmLabel', { name: user.organization_name })} htmlFor="erase-confirm" error={eraseError ?? undefined}>
          <Input
            id="erase-confirm"
            value={confirmName}
            onChange={(e) => setConfirmName(e.target.value)}
            autoComplete="off"
            disabled={erasing}
            invalid={!!eraseError}
          />
        </Field>
      </Dialog>
    </SettingsSection>
  )
}
