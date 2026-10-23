'use client'

import { Pencil } from 'lucide-react'
import { Button, FrameworkBadge } from '@/components/ui'
import type { Client } from '@/lib/types'
import { NOT_AVAILABLE, formatEur, formatInt, formatIsoDate } from './format'

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 py-3 sm:grid-cols-[200px_1fr] sm:gap-6">
      <dt className="text-small text-ink-2">{label}</dt>
      <dd className="text-body text-ink">{children}</dd>
    </div>
  )
}

function Missing({ hint }: { hint?: string }) {
  return <span className="text-ink-3">{hint ?? NOT_AVAILABLE}</span>
}

/** The client's profile as the analyses read it. */
export function ProfileTab({ client, onEdit }: { client: Client; onEdit: () => void }) {
  const frameworks = client.applicable_frameworks ?? []
  const jurisdictions = client.jurisdictions ?? []

  return (
    <div className="rounded-lg border border-rule bg-surface px-5 py-2">
      <dl className="divide-y divide-rule">
        <Row label="Nome">{client.name}</Row>
        <Row label="Settore">{client.sector || <Missing hint="Non indicato" />}</Row>
        <Row label="Dipendenti">
          <span className="tabular">{formatInt(client.employee_count) ?? <Missing hint="Non indicato" />}</span>
        </Row>
        <Row label="Fatturato annuo">
          <span className="tabular">{formatEur(client.revenue_eur) ?? <Missing hint="Non indicato" />}</span>
        </Row>
        <Row label="Paesi in cui opera">
          {jurisdictions.length > 0 ? jurisdictions.join(', ') : <Missing hint="Non indicati" />}
        </Row>
        <Row label="Framework seguiti">
          {frameworks.length > 0 ? (
            <div className="flex flex-wrap gap-1">
              {frameworks.map((fw) => (
                <FrameworkBadge key={fw} framework={fw} />
              ))}
            </div>
          ) : (
            <Missing hint="Nessuno: aggiungili dal profilo per avere analisi e scadenze." />
          )}
        </Row>
        <Row label="Creato il">
          <span className="tabular">{formatIsoDate(client.created_at) ?? <Missing />}</span>
        </Row>
        <Row label="Ultimo aggiornamento">
          <span className="tabular">{formatIsoDate(client.updated_at) ?? <Missing />}</span>
        </Row>
      </dl>
      <div className="border-t border-rule py-4">
        <Button variant="secondary" onClick={onEdit} iconLeft={<Pencil className="h-4 w-4" aria-hidden="true" />}>
          Modifica il profilo
        </Button>
      </div>
    </div>
  )
}
