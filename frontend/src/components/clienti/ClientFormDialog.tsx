'use client'

import { useEffect, useState, type FormEvent } from 'react'
import { useTranslations } from 'next-intl'
import { Button, Checkbox, Dialog, Field, Input, describedBy, frameworkLabel, useToast } from '@/components/ui'
import { useErrorText } from '@/i18n/errors'
import type { Client } from '@/lib/types'
import { FRAMEWORK_KEYS, createClient, updateClient } from './clients-api'
import {
  clientToForm,
  emptyClientForm,
  formToPayload,
  validateClientForm,
  type ClientFormErrors,
  type ClientFormValues,
} from './client-form'

const FORM_ID = 'client-form'

/**
 * Create or edit a client. The same dialog serves both: with `client` it
 * edits, without it creates. Validation messages sit under the field they
 * refer to, in the language of the interface.
 */
export function ClientFormDialog({
  open,
  onClose,
  client,
  onSaved,
}: {
  open: boolean
  onClose: () => void
  client?: Client | null
  onSaved: (saved: Client) => void
}) {
  const t = useTranslations('clienti.form')
  const tRoot = useTranslations()
  const errorText = useErrorText()
  const { toast } = useToast()
  const [values, setValues] = useState<ClientFormValues>(emptyClientForm)
  const [errors, setErrors] = useState<ClientFormErrors>({})
  const [serverError, setServerError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!open) return
    setValues(client ? clientToForm(client) : emptyClientForm())
    setErrors({})
    setServerError(null)
  }, [open, client])

  const set = <K extends keyof ClientFormValues>(key: K, value: ClientFormValues[K]) => {
    setValues((prev) => ({ ...prev, [key]: value }))
    if (errors[key]) setErrors((prev) => ({ ...prev, [key]: undefined }))
  }

  const toggleFramework = (key: string) => {
    setValues((prev) => ({
      ...prev,
      applicable_frameworks: prev.applicable_frameworks.includes(key)
        ? prev.applicable_frameworks.filter((f) => f !== key)
        : [...prev.applicable_frameworks, key],
    }))
  }

  // Known frameworks first, then any value already on the client that the
  // backend enum does not list (legacy labels stay selectable, never dropped).
  const frameworkOptions = [
    ...FRAMEWORK_KEYS,
    ...values.applicable_frameworks.filter((f) => !(FRAMEWORK_KEYS as readonly string[]).includes(f)),
  ]

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const found = validateClientForm(values, tRoot)
    setErrors(found)
    if (Object.keys(found).length > 0) {
      const first = Object.keys(found)[0]
      document.getElementById(`cl-${first}`)?.focus()
      return
    }
    setSaving(true)
    setServerError(null)
    try {
      const payload = formToPayload(values)
      const saved = client ? await updateClient(client.id, payload) : await createClient(payload)
      const merged: Client = { ...(client ?? {}), ...saved } as Client
      toast({
        kind: 'ok',
        title: client ? t('savedTitle') : t('createdTitle'),
        description: merged.name,
      })
      onSaved(merged)
      onClose()
    } catch (err) {
      setServerError(errorText(err, 'clienti.form.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={client ? t('titleEdit') : t('titleNew')}
      description={client ? t('descriptionEdit') : t('descriptionNew')}
      footer={
        <>
          <Button type="button" variant="secondary" onClick={onClose} disabled={saving}>
            {t('cancel')}
          </Button>
          <Button type="submit" form={FORM_ID} loading={saving}>
            {client ? t('save') : t('create')}
          </Button>
        </>
      }
    >
      <form id={FORM_ID} onSubmit={submit} noValidate className="space-y-4">
        {serverError && (
          <p role="alert" className="rounded-md border border-bad/30 bg-bad/10 px-3 py-2 text-small text-bad">
            {serverError}
          </p>
        )}

        <Field label={t('name')} htmlFor="cl-name" required error={errors.name}>
          <Input
            id="cl-name"
            value={values.name}
            onChange={(e) => set('name', e.target.value)}
            maxLength={255}
            autoComplete="organization"
            placeholder={t('namePlaceholder')}
            invalid={!!errors.name}
            aria-describedby={describedBy('cl-name', { error: errors.name })}
          />
        </Field>

        <Field label={t('sector')} htmlFor="cl-sector" error={errors.sector}>
          <Input
            id="cl-sector"
            value={values.sector}
            onChange={(e) => set('sector', e.target.value)}
            maxLength={100}
            placeholder={t('sectorPlaceholder')}
            invalid={!!errors.sector}
            aria-describedby={describedBy('cl-sector', { error: errors.sector })}
          />
        </Field>

        <div className="grid grid-cols-2 gap-4">
          <Field label={t('employees')} htmlFor="cl-employee_count" error={errors.employee_count}>
            <Input
              id="cl-employee_count"
              inputMode="numeric"
              value={values.employee_count}
              onChange={(e) => set('employee_count', e.target.value)}
              placeholder="2500"
              invalid={!!errors.employee_count}
              aria-describedby={describedBy('cl-employee_count', { error: errors.employee_count })}
            />
          </Field>
          <Field
            label={t('revenue')}
            htmlFor="cl-revenue_eur"
            help={errors.revenue_eur ? undefined : t('revenueHelp')}
            error={errors.revenue_eur}
          >
            <Input
              id="cl-revenue_eur"
              inputMode="numeric"
              value={values.revenue_eur}
              onChange={(e) => set('revenue_eur', e.target.value)}
              placeholder="200000000"
              invalid={!!errors.revenue_eur}
              aria-describedby={describedBy('cl-revenue_eur', {
                error: errors.revenue_eur,
                help: true,
              })}
            />
          </Field>
        </div>

        <Field
          label={t('countries')}
          htmlFor="cl-jurisdictions"
          help={errors.jurisdictions ? undefined : t('countriesHelp')}
          error={errors.jurisdictions}
        >
          <Input
            id="cl-jurisdictions"
            value={values.jurisdictions}
            onChange={(e) => set('jurisdictions', e.target.value)}
            placeholder="IT, DE, FR"
            invalid={!!errors.jurisdictions}
            aria-describedby={describedBy('cl-jurisdictions', {
              error: errors.jurisdictions,
              help: true,
            })}
          />
        </Field>

        <fieldset>
          <legend className="text-small font-medium text-ink">{t('frameworks')}</legend>
          <p className="mt-1 text-caption text-ink-3">{t('frameworksHelp')}</p>
          <div className="mt-2 grid grid-cols-2 gap-2">
            {frameworkOptions.map((key) => (
              <Checkbox
                key={key}
                id={`cl-fw-${key}`}
                label={frameworkLabel(key, tRoot)}
                checked={values.applicable_frameworks.includes(key)}
                onChange={() => toggleFramework(key)}
              />
            ))}
          </div>
        </fieldset>
      </form>
    </Dialog>
  )
}
