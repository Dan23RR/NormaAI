'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { CheckCircle2, FileText } from 'lucide-react'
import { Button, ButtonLink } from '@/components/ui/Button'
import { Field, Input, Select } from '@/components/ui/Field'

// Lead submission target: always the same-origin serverless route. It emails
// the Codex through Resend and never depends on the backend being up.
const LEADS_ENDPOINT = '/api/leads'

// The role travels to the founder's inbox as it always did (Italian values);
// only the option labels follow the interface language.
const ROLES = [
  { value: 'Compliance officer / DPO', key: 'compliance' },
  { value: 'CFO / Risk manager', key: 'cfo' },
  { value: 'Avvocato / Consulente', key: 'lawyer' },
  { value: 'Altro', key: 'other' },
] as const

type FormStatus =
  | { kind: 'idle' }
  | { kind: 'submitting' }
  | { kind: 'success'; message: string; downloadUrl?: string }
  | { kind: 'error'; message: string }

export function CodexForm() {
  const t = useTranslations('site.codexForm')
  const [status, setStatus] = useState<FormStatus>({ kind: 'idle' })

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (status.kind === 'submitting') return

    const fd = new FormData(e.currentTarget)
    // Outreach emails land on /codex?lead=<id> (redirected to /?lead=<id>);
    // forward that id so the founder notification ties back to the prospect.
    const leadRef =
      typeof window !== 'undefined'
        ? new URLSearchParams(window.location.search).get('lead') || undefined
        : undefined
    const payload = {
      email: String(fd.get('email') || '').trim(),
      org_name: String(fd.get('org') || '').trim() || undefined,
      role: String(fd.get('role') || '').trim() || undefined,
      source: 'codex_download',
      lead_ref: leadRef,
      contact_time: String(fd.get('contact_time') || ''), // honeypot (autofill-safe name)
    }

    if (!payload.email || !/.+@.+\..+/.test(payload.email)) {
      setStatus({ kind: 'error', message: t('invalidEmail') })
      return
    }

    setStatus({ kind: 'submitting' })

    try {
      const res = await fetch(LEADS_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(payload),
      })

      if (res.status === 201 || res.status === 200) {
        const data = await res.json().catch(() => ({}))
        const downloadUrl: string | undefined = data?.download_url
        setStatus({
          kind: 'success',
          message: data?.message || t('successDefault'),
          downloadUrl,
        })
        return
      }

      if (res.status === 429) {
        setStatus({ kind: 'error', message: t('tooMany') })
        return
      }

      if (res.status === 422) {
        setStatus({ kind: 'error', message: t('invalidData') })
        return
      }

      setStatus({ kind: 'error', message: t('unexpected', { status: String(res.status) }) })
    } catch {
      setStatus({ kind: 'error', message: t('unreachable') })
    }
  }

  if (status.kind === 'success') {
    return (
      <div className="rounded-lg border border-ok/30 bg-surface p-6">
        <div className="flex items-start gap-3">
          <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-ok" aria-hidden="true" />
          <div>
            <h3 className="text-h4">{t('received')}</h3>
            <p className="mt-1 text-small text-ink-2">{status.message}</p>
          </div>
        </div>
        {status.downloadUrl && (
          <ButtonLink href={status.downloadUrl} external className="mt-5 w-full" iconLeft={<FileText className="h-4 w-4" aria-hidden="true" />}>
            {t('download')}
          </ButtonLink>
        )}
        <p className="mt-4 text-caption text-ink-3">
          {t.rich('talk', {
            mail: (chunks) => (
              <a href="mailto:info@normaai.org?subject=NormaAI%20demo" className="text-union hover:underline">
                {chunks}
              </a>
            ),
          })}
        </p>
      </div>
    )
  }

  const busy = status.kind === 'submitting'

  return (
    <form className="rounded-lg border border-rule bg-surface p-6" onSubmit={handleSubmit} noValidate>
      {/* Honeypot: invisible to humans, bots fill it and get silently dropped.
          The field name matches no browser autofill category. */}
      <input
        type="text"
        name="contact_time"
        tabIndex={-1}
        autoComplete="off"
        aria-hidden="true"
        className="absolute -left-[9999px] h-0 w-0 opacity-0"
      />
      <div className="space-y-4">
        <Field label={t('email')} htmlFor="codex-email" required>
          <Input id="codex-email" name="email" type="email" required autoComplete="email" inputMode="email" placeholder={t('emailPlaceholder')} disabled={busy} />
        </Field>
        <Field label={t('org')} htmlFor="codex-org">
          <Input id="codex-org" name="org" autoComplete="organization" placeholder={t('orgPlaceholder')} disabled={busy} />
        </Field>
        <Field label={t('role')} htmlFor="codex-role">
          <Select id="codex-role" name="role" defaultValue={ROLES[0].value} disabled={busy}>
            {ROLES.map((role) => (
              <option key={role.key} value={role.value}>
                {t(`roles.${role.key}`)}
              </option>
            ))}
          </Select>
        </Field>
      </div>
      <Button type="submit" loading={busy} className="mt-5 w-full" size="lg">
        {t('submit')}
      </Button>
      {status.kind === 'error' && (
        <p role="alert" className="mt-3 rounded-md border border-bad/30 bg-bad/5 px-3 py-2 text-small text-bad">
          {status.message}
        </p>
      )}
      <p className="mt-3 text-caption text-ink-3">{t('noNewsletter')}</p>
    </form>
  )
}
