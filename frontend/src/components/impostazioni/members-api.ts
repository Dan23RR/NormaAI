import type { BadgeTone } from '@/components/ui'
import { api } from '@/lib/api'
import { ApiError } from '@/lib/api-error'
import { isDemoMode } from '@/lib/auth'
import { DEMO_USER } from '@/lib/mock-data'

/**
 * The members of the caller's organisation, against src/auth/router.py
 * (all three are admin only):
 * - GET    /api/v1/auth/members             -> the accounts, oldest first
 * - PATCH  /api/v1/auth/members/{id} {role} -> the member with the new role
 * - DELETE /api/v1/auth/members/{id}        -> 204: the account and its own
 *   conversations are deleted; clients, checks, reports and invites stay
 * The API refuses to demote or remove the last active admin (409) and says
 * why in `detail`, which the interface shows as it comes. A backend without
 * the list answers 404: ApiError 'membersUnavailable'. In the demo the members
 * are examples, and their changes last until the page is reloaded.
 */

export type MemberRole = 'admin' | 'member' | 'viewer'

export const MEMBER_ROLES: MemberRole[] = ['admin', 'member', 'viewer']

export interface Member {
  id: string
  email: string
  name: string
  role: MemberRole
  is_active: boolean
  email_verified: boolean
  created_at: string | null
}

const MEMBERS_PATH = '/api/v1/auth/members'

function memberPath(id: string): string {
  return `${MEMBERS_PATH}/${encodeURIComponent(id)}`
}

// The backend treats any role other than admin and viewer as an editor, that is a member.
function asRole(value: unknown): MemberRole {
  return value === 'admin' || value === 'viewer' ? value : 'member'
}

export function normalizeMember(raw: unknown): Member {
  const r = (raw ?? {}) as Record<string, unknown>
  return {
    id: String(r.id ?? ''),
    email: String(r.email ?? ''),
    name: typeof r.name === 'string' ? r.name : '',
    role: asRole(r.role),
    // A field the server left out claims no problem.
    is_active: r.is_active !== false,
    email_verified: r.email_verified !== false,
    created_at: typeof r.created_at === 'string' ? r.created_at : null,
  }
}

export function normalizeMembers(res: unknown): Member[] {
  return Array.isArray(res) ? res.map(normalizeMember) : []
}

export function isMembersUnavailable(err: unknown): boolean {
  return err instanceof ApiError && err.code === 'membersUnavailable'
}

/** The server answered 404: no such member (any more), or no such endpoint. */
export function isNotFound(err: unknown): boolean {
  return err instanceof ApiError && err.values?.status === '404'
}

// ─── Demo ────────────────────────────────────────────────────

const DEMO_MEMBERS: Member[] = [
  {
    id: DEMO_USER.id,
    email: DEMO_USER.email,
    name: DEMO_USER.name,
    role: 'admin',
    is_active: true,
    email_verified: true,
    created_at: '2026-01-12T09:00:00Z',
  },
  {
    id: 'demo-member-002',
    email: 'marco@studio-esempio.example',
    name: 'Marco Esempio',
    role: 'member',
    is_active: true,
    email_verified: true,
    created_at: '2026-02-03T09:00:00Z',
  },
  {
    id: 'demo-member-003',
    email: 'sara@studio-esempio.example',
    name: 'Sara Esempio',
    role: 'viewer',
    is_active: true,
    email_verified: false,
    created_at: '2026-03-17T09:00:00Z',
  },
]

// Kept in memory, not in the browser's storage: a reload brings the examples back.
let demoMembers: Member[] | null = null

function demoStore(): Member[] {
  if (!demoMembers) demoMembers = DEMO_MEMBERS.map((m) => ({ ...m }))
  return demoMembers
}

/** Back to the example members of the demo. */
export function resetDemoMembers(): void {
  demoMembers = null
}

function demoNotFound(): ApiError {
  return new ApiError('requestFailed', { values: { status: '404' } })
}

// ─── Calls ───────────────────────────────────────────────────

export async function listMembers(): Promise<Member[]> {
  if (isDemoMode()) return demoStore().map((m) => ({ ...m }))
  try {
    return normalizeMembers(await api.get<unknown>(MEMBERS_PATH))
  } catch (err) {
    if (isNotFound(err)) throw new ApiError('membersUnavailable')
    throw err
  }
}

export async function changeMemberRole(id: string, role: MemberRole): Promise<Member> {
  if (isDemoMode()) {
    const member = demoStore().find((m) => m.id === id)
    if (!member) throw demoNotFound()
    member.role = role
    return { ...member }
  }
  return normalizeMember(await api.patch<unknown>(memberPath(id), { role }))
}

export async function removeMember(id: string): Promise<void> {
  if (isDemoMode()) {
    const store = demoStore()
    const index = store.findIndex((m) => m.id === id)
    if (index < 0) throw demoNotFound()
    store.splice(index, 1)
    return
  }
  await api.del<void>(memberPath(id))
}

// ─── Labels ──────────────────────────────────────────────────

export type MemberState = 'active' | 'unverified' | 'inactive'

export function memberState(member: Member): MemberState {
  if (!member.is_active) return 'inactive'
  if (!member.email_verified) return 'unverified'
  return 'active'
}

export const MEMBER_STATE_TONE: Record<MemberState, BadgeTone> = {
  active: 'ok',
  unverified: 'warn',
  inactive: 'neutral',
}

/** The name to show; the email when the account has none. */
export function memberName(member: Member): string {
  return member.name.trim() || member.email
}
