import { api } from '@/lib/api'
import { isDemoMode } from '@/lib/auth'
import { DEMO_CLIENTS } from '@/lib/mock-data'

export interface ClientOption {
  id: string
  name: string
  sector?: string
  employee_count?: number
  revenue_eur?: number
  jurisdictions?: string[]
}

/**
 * The clients endpoint answers with a plain array (backend) or with
 * { clients, data, total } (demo); both become the same list here.
 */
export function normaliseClients(raw: unknown): ClientOption[] {
  const list: unknown[] = Array.isArray(raw)
    ? raw
    : ((raw as { clients?: unknown[]; data?: unknown[] } | null)?.clients ??
      (raw as { data?: unknown[] } | null)?.data ??
      [])
  const out: ClientOption[] = []
  for (const item of list) {
    if (!item || typeof item !== 'object') continue
    const c = item as Record<string, unknown>
    if (typeof c.id !== 'string' || typeof c.name !== 'string') continue
    out.push({
      id: c.id,
      name: c.name,
      sector: typeof c.sector === 'string' ? c.sector : undefined,
      employee_count: typeof c.employee_count === 'number' ? c.employee_count : undefined,
      revenue_eur: typeof c.revenue_eur === 'number' ? c.revenue_eur : undefined,
      jurisdictions: Array.isArray(c.jurisdictions)
        ? c.jurisdictions.filter((j): j is string => typeof j === 'string')
        : undefined,
    })
  }
  return out
}

/** Demo mode reads the sample clients directly; otherwise the organization's clients come from the API. */
export async function loadClients(): Promise<ClientOption[]> {
  if (isDemoMode()) return normaliseClients(DEMO_CLIENTS)
  return normaliseClients(await api.get<unknown>('/api/v1/clients'))
}
