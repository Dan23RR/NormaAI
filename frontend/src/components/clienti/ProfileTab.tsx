'use client'

import { useFormatter, useTranslations } from 'next-intl'
import { Pencil } from 'lucide-react'
import { Button, FrameworkBadge } from '@/components/ui'
import { EUR, INT } from '@/i18n/format'
import type { Client } from '@/lib/types'
import { formatIsoDate } from './format'

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 py-3 sm:grid-cols-[200px_1fr] sm:gap-6">
      <dt className="text-small text-ink-2">{label}</dt>
      <dd className="text-body text-ink">{children}</dd>
    </div>
  )
}

function Missing({ hint }: { hint?: string }) {
  const t = useTranslations('ui')
  return <span className="text-ink-3">{hint ?? t('notAvailable')}</span>
}

/** The client's profile as the analyses read it. */
export function ProfileTab({ client, onEdit }: { client: Client; onEdit: () => void }) {
  const t = useTranslations('clienti.profile')
  const format = useFormatter()
  const frameworks = client.applicable_frameworks ?? []
  const jurisdictions = client.jurisdictions ?? []
  const employees = typeof client.employee_count === 'number' ? format.number(client.employee_count, INT) : null
  const revenue = typeof client.revenue_eur === 'number' ? format.number(client.revenue_eur, EUR) : null

  return (
    <div className="rounded-lg border border-rule bg-surface px-5 py-2">
      <dl className="divide-y divide-rule">
        <Row label={t('name')}>{client.name}</Row>
        <Row label={t('sector')}>{client.sector || <Missing hint={t('notGiven')} />}</Row>
        <Row label={t('employees')}>
          <span className="tabular">{employees ?? <Missing hint={t('notGiven')} />}</span>
        </Row>
        <Row label={t('revenue')}>
          <span className="tabular">{revenue ?? <Missing hint={t('notGiven')} />}</span>
        </Row>
        <Row label={t('countries')}>
          {jurisdictions.length > 0 ? jurisdictions.join(', ') : <Missing hint={t('notGivenPlural')} />}
        </Row>
        <Row label={t('frameworks')}>
          {frameworks.length > 0 ? (
            <div className="flex flex-wrap gap-1">
              {frameworks.map((fw) => (
                <FrameworkBadge key={fw} framework={fw} />
              ))}
            </div>
          ) : (
            <Missing hint={t('noFrameworks')} />
          )}
        </Row>
        <Row label={t('created')}>
          <span className="tabular">{formatIsoDate(client.created_at) ?? <Missing />}</span>
        </Row>
        <Row label={t('updated')}>
          <span className="tabular">{formatIsoDate(client.updated_at) ?? <Missing />}</span>
        </Row>
      </dl>
      <div className="border-t border-rule py-4">
        <Button variant="secondary" onClick={onEdit} iconLeft={<Pencil className="h-4 w-4" aria-hidden="true" />}>
          {t('edit')}
        </Button>
      </div>
    </div>
  )
}
