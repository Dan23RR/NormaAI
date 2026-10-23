import type { BadgeTone } from '@/components/ui'
import type { Translate } from '@/i18n/types'
import { api } from '@/lib/api'
import { ApiError } from '@/lib/api-error'
import { isDemoMode } from '@/lib/auth'

/**
 * Invitations, against the backend contract in src/auth/router.py:
 * - POST /api/v1/auth/invites {email, role?, expires_in_days?} -> 201, the
 *   invite plus `code` (plaintext, shown only in that response)
 * - GET  /api/v1/auth/invites -> the caller's organization's invites, no code
 * An older backend answers 404: the page says so (ApiError 'invitesUnavailable')
 * instead of failing silently. In the demo the invitations live in
 * sessionStorage, declared as such.
 */

export type InviteRole = 'member' | 'viewer' | 'admin'
export type InviteStatus = 'pending' | 'used' | 'expired'

export const INVITE_ROLES: InviteRole[] = ['member', 'viewer', 'admin']

export interface Invite {
  id: string
  email: string
  organization_id: string | null
  role: InviteRole
  status: InviteStatus
  created_at: string
  expires_at: string
  used_at: string | null
}

export interface CreatedInvite extends Invite {
  code: string
}

export function isInvitesUnavailable(err: unknown): boolean {
  return err instanceof ApiError && err.code === 'invitesUnavailable'
}

function isNotFound(err: unknown): boolean {
  if (err instanceof ApiError) return err.values?.status === '404' || /not found|\b404\b/i.test(err.message)
  return err instanceof Error && /not found|\b404\b/i.test(err.message)
}

function asRole(value: unknown): InviteRole {
  return value === 'admin' || value === 'viewer' ? value : 'member'
}

function asStatus(r: Record<string, unknown>): InviteStatus {
  if (r.status === 'used' || r.status === 'expired' || r.status === 'pending') return r.status
  if (r.used === true || typeof r.used_at === 'string') return 'used'
  return 'pending'
}

export function normalizeInvite(raw: unknown): Invite {
  const r = (raw ?? {}) as Record<string, unknown>
  return {
    id: String(r.id ?? r.code ?? ''),
    email: String(r.email ?? ''),
    organization_id: typeof r.organization_id === 'string' ? r.organization_id : null,
    role: asRole(r.role),
    status: asStatus(r),
    created_at: typeof r.created_at === 'string' ? r.created_at : '',
    expires_at: typeof r.expires_at === 'string' ? r.expires_at : '',
    used_at: typeof r.used_at === 'string' ? r.used_at : null,
  }
}

export function normalizeInvites(res: unknown): Invite[] {
  const list = Array.isArray(res)
    ? res
    : (res as { data?: unknown; invites?: unknown } | null)?.data ?? (res as { invites?: unknown } | null)?.invites
  if (!Array.isArray(list)) return []
  return list.map(normalizeInvite)
}

const DEMO_INVITES_KEY = 'normaai_demo_invites'
const DEMO_EXPIRY_DAYS = 14

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
    if (isNotFound(err)) throw new ApiError('invitesUnavailable')
    throw err
  }
}

export async function createInvite(email: string, role: InviteRole = 'member'): Promise<CreatedInvite> {
  if (isDemoMode()) {
    const now = new Date()
    const code = demoCode()
    const invite: CreatedInvite = {
      id: `demo-${code}`,
      code,
      email,
      organization_id: null,
      role,
      status: 'pending',
      created_at: now.toISOString(),
      expires_at: new Date(now.getTime() + DEMO_EXPIRY_DAYS * 86_400_000).toISOString(),
      used_at: null,
    }
    writeDemoInvites([invite, ...readDemoInvites()])
    return invite
  }
  try {
    const res = await api.post<unknown>('/api/v1/auth/invites', { email, role })
    const r = (res ?? {}) as Record<string, unknown>
    return { ...normalizeInvite(r), code: String(r.code ?? '') }
  } catch (err) {
    if (isNotFound(err)) throw new ApiError('invitesUnavailable')
    throw err
  }
}

export type InviteState = 'used' | 'expired' | 'active'

export function inviteState(invite: Invite, now: number = Date.now()): InviteState {
  if (invite.status === 'used') return 'used'
  if (invite.status === 'expired') return 'expired'
  const expiry = Date.parse(invite.expires_at)
  if (!Number.isNaN(expiry) && expiry < now) return 'expired'
  return 'active'
}

const STATE_TONE: Record<InviteState, BadgeTone> = { used: 'ok', expired: 'neutral', active: 'union' }

export function inviteStatus(invite: Invite, t: Translate, now: number = Date.now()): { label: string; tone: BadgeTone } {
  const state = inviteState(invite, now)
  return { label: t(`admin.invites.status.${state}`), tone: STATE_TONE[state] }
}

export function inviteRoleLabel(role: InviteRole, t: Translate): string {
  return t(`admin.invites.roles.${role}`)
}

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/

/** The key of the problem under `admin.invites.errors`, or null when the email is fine. */
export function validateInviteEmail(value: string): 'emailRequired' | 'emailInvalid' | null {
  const email = value.trim()
  if (!email) return 'emailRequired'
  if (!EMAIL.test(email)) return 'emailInvalid'
  return null
}
