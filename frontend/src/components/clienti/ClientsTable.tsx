'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { FrameworkBadge, TBody, TD, TH, THead, TR, Table } from '@/components/ui'
import type { Client } from '@/lib/types'
import { NOT_AVAILABLE, formatEur, formatInt, formatIsoDate } from './format'

function Missing() {
  return <span className="text-ink-3">{NOT_AVAILABLE}</span>
}

/** The list of clients: a row per client, the name links to the detail. */
export function ClientsTable({ clients }: { clients: Client[] }) {
  const router = useRouter()

  return (
    <Table>
      <THead>
        <TR>
          <TH>Nome</TH>
          <TH className="hidden md:table-cell">Settore</TH>
          <TH numeric className="hidden sm:table-cell">
            Dipendenti
          </TH>
          <TH numeric className="hidden lg:table-cell">
            Fatturato
          </TH>
          <TH>Framework</TH>
          <TH className="hidden md:table-cell">Ultimo aggiornamento</TH>
        </TR>
      </THead>
      <TBody>
        {clients.map((client) => {
          const href = `/app/clienti/${encodeURIComponent(client.id)}`
          const employees = formatInt(client.employee_count)
          const revenue = formatEur(client.revenue_eur)
          const updated = formatIsoDate(client.updated_at)
          const frameworks = client.applicable_frameworks ?? []
          return (
            <TR
              key={client.id}
              className="cursor-pointer transition-colors hover:bg-surface-3"
              onClick={() => router.push(href)}
            >
              <TD>
                <Link
                  href={href}
                  className="font-medium text-ink no-underline hover:underline"
                  onClick={(e) => e.stopPropagation()}
                >
                  {client.name}
                </Link>
                {client.sector && <p className="mt-0.5 text-caption text-ink-3 md:hidden">{client.sector}</p>}
              </TD>
              <TD className="hidden text-ink-2 md:table-cell">{client.sector || <Missing />}</TD>
              <TD numeric className="hidden sm:table-cell">
                {employees ?? <Missing />}
              </TD>
              <TD numeric className="hidden lg:table-cell">
                {revenue ?? <Missing />}
              </TD>
              <TD>
                {frameworks.length > 0 ? (
                  <div className="flex flex-wrap gap-1">
                    {frameworks.map((fw) => (
                      <FrameworkBadge key={fw} framework={fw} />
                    ))}
                  </div>
                ) : (
                  <span className="text-caption text-ink-3">Nessuno</span>
                )}
              </TD>
              <TD className="hidden tabular text-ink-2 md:table-cell">{updated ?? <Missing />}</TD>
            </TR>
          )
        })}
      </TBody>
    </Table>
  )
}
