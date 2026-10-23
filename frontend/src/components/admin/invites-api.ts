import { api } from '@/lib/api'
import { isDemoMode } from '@/lib/auth'
import type { BadgeTone } from '@/components/ui'

/**
 * Invitations, against the contract the backend is adding on its own branch:
 * - POST /api/v1/auth/invites {email, organization_id?} -> {code, email, expires_at}
 * - GET  /api/v1/auth/invites -> [{code, email, organization_id, used, expires_at, created_at}]
 * An older backend answers 404: the page says so instead of failing silently.
 * In the demo the invitations live in sessionStorage, declared as such.
 */

export interface Invite {
  code: string
  email: string
  organization_id?: string | null
  used: boolean
  expires_at: string
  created_at: string
}

export interface CreatedInvite {
  code: string
  email: string
  expires_at: string
}

export class InvitesUnavailableError extends Error {
  constructor() {
    super('Il server in uso non ha ancora gli inviti (endpoint /api/v1/auth/invites non trovato).')
    this.name = 'InvitesUnavailableError'
  }
}

function isNotFound(err: unknown): boolean {
  return err instanceof Error && /not found|\b404\b/i.test(err.message)
}

export function normalizeInvites(res: unknown): Invite[] {
  const list = Array.isArray(res)
    ? res
    : (res as { data?: unknown; invites?: unknown } | null)?.data ?? (res as { invites?: unknown } | null)?.invites
  if (!Array.isArray(list)) return []
  return list.map((raw) => {
    const r = (raw ?? {}) as Record<string, unknown>
    return {
      code: String(r.code ?? ''),
      email: String(r.email ?? ''),
      organization_id: typeof r.organization_id === 'string' ? r.organization_id : null,
      used: Boolean(r.used),
      expires_at: typeof r.expires_at === 'string' ? r.expires_at : '',
      created_at: typeof r.created_at === 'string' ? r.created_at : '',
    }
  })
}

const DEMO_INVITES_KEY = 'normaai_demo_invites'
const DEMO_EXPIRY_DAYS = 7

function readDemoInvites(): Invite[] {
  try {
    const raw = sessionStorage.getItem(DEMO_INVITES_KEY)
    return raw ? normalizeInvites(JSON.parse(raw)) : []
  } catch {
    return []
  }
}

function writeDemoInvites(list: Invite[]) {
  try {
    sessionStorage.setItem(DEMO_INVITES_KEY, JSON.stringify(list))
  } catch {
    /* the list stays in memory for this page only */
  }
}

function demoCode(): string {
  const alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
  let code = ''
  for (let i = 0; i < 8; i++) code += alphabet[Math.floor(Math.random() * alphabet.length)]
  return code
}

export async function listInvites(): Promise<Invite[]> {
  if (isDemoMode()) return readDemoInvites()
  try {
    return normalizeInvites(await api.get<unknown>('/api/v1/auth/invites'))
  } catch (err) {
    if (isNotFound(err)) throw new InvitesUnavailableError()
    throw err
  }
}

export async function createInvite(email: string): Promise<CreatedInvite> {
  if (isDemoMode()) {
    const now = new Date()
    const invite: Invite = {
      code: demoCode(),
      email,
      organization_id: null,
      used: false,
      created_at: now.toISOString(),
      expires_at: new Date(now.getTime() + DEMO_EXPIRY_DAYS * 86_400_000).toISOString(),
    }
    writeDemoInvites([invite, ...readDemoInvites()])
    return { code: invite.code, email: invite.email, expires_at: invite.expires_at }
  }
  try {
    return await api.post<CreatedInvite>('/api/v1/auth/invites', { email })
  } catch (err) {
    if (isNotFound(err)) throw new InvitesUnavailableError()
    throw err
  }
}

export function inviteStatus(invite: Invite, now: number = Date.now()): { label: string; tone: BadgeTone } {
  if (invite.used) return { label: 'Usato', tone: 'ok' }
  const expiry = Date.parse(invite.expires_at)
  if (!Number.isNaN(expiry) && expiry < now) return { label: 'Scaduto', tone: 'neutral' }
  return { label: 'Attivo', tone: 'union' }
}

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/

export function validateInviteEmail(value: string): string | null {
  const email = value.trim()
  if (!email) return 'Inserisci l’email della persona da invitare.'
  if (!EMAIL.test(email)) return 'L’email non sembra valida: controlla che abbia la forma nome@dominio.it.'
  return null
}
