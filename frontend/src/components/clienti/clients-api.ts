import { api } from '@/lib/api'
import type { Client } from '@/lib/types'

/**
 * Client CRUD against src/api/routers/clients.py.
 *
 * - GET    /api/v1/clients       -> ClientResponse[] (the demo client wraps it in {data, clients, total})
 * - POST   /api/v1/clients       -> ClientResponse (201)
 * - GET    /api/v1/clients/{id}  -> ClientResponse (the demo client answers with the whole list)
 * - PUT    /api/v1/clients/{id}  -> ClientResponse, only the fields sent are updated
 * - DELETE /api/v1/clients/{id}  -> 204, no body
 */

/** The frameworks the backend accepts (FrameworkEnum in src/api/schemas.py). */
export const FRAMEWORK_KEYS = ['CSRD', 'CSDDD', 'AI_ACT', 'DORA', 'NIS2', 'TAXONOMY', 'GDPR', 'CRA'] as const
export type FrameworkKey = (typeof FRAMEWORK_KEYS)[number]

export function isFrameworkKey(value: string): value is FrameworkKey {
  return (FRAMEWORK_KEYS as readonly string[]).includes(value)
}

/** What the API receives for a client: optional fields may be null. */
export interface ClientPayload {
  name: string
  sector: string | null
  employee_count: number | null
  revenue_eur: number | null
  jurisdictions: string[]
  applicable_frameworks: string[]
}

export function normalizeClientList(res: unknown): Client[] {
  if (Array.isArray(res)) return res as Client[]
  if (res && typeof res === 'object') {
    const obj = res as { data?: unknown; clients?: unknown }
    if (Array.isArray(obj.data)) return obj.data as Client[]
    if (Array.isArray(obj.clients)) return obj.clients as Client[]
  }
  return []
}

export async function fetchClients(): Promise<Client[]> {
  const res = await api.get<unknown>('/api/v1/clients')
  return normalizeClientList(res)
}

export async function fetchClient(id: string): Promise<Client | null> {
  const res = await api.get<unknown>(`/api/v1/clients/${encodeURIComponent(id)}`)
  if (res && typeof res === 'object' && !Array.isArray(res) && (res as { id?: unknown }).id === id) {
    return res as Client
  }
  return normalizeClientList(res).find((c) => c.id === id) ?? null
}

export function createClient(payload: ClientPayload): Promise<Client> {
  return api.post<Client>('/api/v1/clients', payload)
}

export function updateClient(id: string, payload: ClientPayload): Promise<Client> {
  return api.put<Client>(`/api/v1/clients/${encodeURIComponent(id)}`, payload)
}

export async function deleteClient(id: string): Promise<void> {
  try {
    await api.del<unknown>(`/api/v1/clients/${encodeURIComponent(id)}`)
  } catch (err) {
    // The backend answers 204 No Content and the api client always parses the
    // body as JSON: an empty body means the deletion succeeded.
    if (err instanceof SyntaxError) return
    throw err
  }
}
