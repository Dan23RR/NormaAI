import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest'
import { ApiError } from '@/lib/api-error'

const auth = vi.hoisted(() => ({ demo: false }))

vi.mock('@/lib/api', () => ({
  api: { get: vi.fn(), patch: vi.fn(), del: vi.fn() },
}))

vi.mock('@/lib/auth', () => ({
  isDemoMode: () => auth.demo,
}))

import { api } from '@/lib/api'
import {
  changeMemberRole,
  isMembersUnavailable,
  isNotFound,
  listMembers,
  memberName,
  memberState,
  normalizeMember,
  removeMember,
  resetDemoMembers,
  type Member,
} from '../members-api'

const ANNA = {
  id: '6f1c2a4e-0000-4000-8000-000000000001',
  email: 'anna@studio.example',
  name: 'Anna Rossi',
  role: 'admin',
  is_active: true,
  email_verified: true,
  created_at: '2026-11-02T09:00:00Z',
}

const LUCA = {
  id: '6f1c2a4e-0000-4000-8000-000000000002',
  email: 'luca@studio.example',
  name: 'Luca Neri',
  role: 'member',
  is_active: true,
  email_verified: false,
  created_at: '2026-11-03T09:00:00Z',
}

function failed(status: number, detail?: string) {
  return new ApiError('requestFailed', { detail, values: { status: String(status) } })
}

const LAST_ADMIN =
  "L'organizzazione deve avere almeno un amministratore attivo: nomina prima un altro amministratore."

describe('members API client', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    auth.demo = false
  })

  it('lists the members of the organisation', async () => {
    ;(api.get as Mock).mockResolvedValue([ANNA, LUCA])
    const members = await listMembers()
    expect(api.get).toHaveBeenCalledWith('/api/v1/auth/members')
    expect(members).toEqual([ANNA, LUCA])
  })

  it('reads a member defensively', () => {
    expect(normalizeMember({ id: 7, email: 'x@y.example', role: 'owner' })).toEqual({
      id: '7',
      email: 'x@y.example',
      name: '',
      // Neither admin nor viewer: the backend lets it edit, like a member.
      role: 'member',
      // Fields the server left out claim no problem.
      is_active: true,
      email_verified: true,
      created_at: null,
    })
    expect(normalizeMember(null).id).toBe('')
  })

  it('says when the server has no member list yet', async () => {
    ;(api.get as Mock).mockRejectedValue(failed(404, 'Not Found'))
    const err = await listMembers().catch((e: unknown) => e)
    expect(isMembersUnavailable(err)).toBe(true)
    expect((err as ApiError).code).toBe('membersUnavailable')
  })

  it('passes on any other refusal with the server’s words', async () => {
    const forbidden = failed(403, "Operazione riservata agli amministratori dell'organizzazione.")
    ;(api.get as Mock).mockRejectedValue(forbidden)
    await expect(listMembers()).rejects.toBe(forbidden)
    expect(isMembersUnavailable(forbidden)).toBe(false)
  })

  it('changes a role with PATCH and returns the member as saved', async () => {
    ;(api.patch as Mock).mockResolvedValue({ ...LUCA, role: 'viewer' })
    const member = await changeMemberRole(LUCA.id, 'viewer')
    expect(api.patch).toHaveBeenCalledWith(`/api/v1/auth/members/${LUCA.id}`, { role: 'viewer' })
    expect(member.role).toBe('viewer')
  })

  it('puts the id in the path as a single, encoded segment', async () => {
    ;(api.patch as Mock).mockResolvedValue(LUCA)
    ;(api.del as Mock).mockResolvedValue(undefined)
    await changeMemberRole('a/b?c', 'member')
    await removeMember('a/b?c')
    expect(api.patch).toHaveBeenCalledWith('/api/v1/auth/members/a%2Fb%3Fc', { role: 'member' })
    expect(api.del).toHaveBeenCalledWith('/api/v1/auth/members/a%2Fb%3Fc')
  })

  it('lets the refusal for the last admin through, detail included', async () => {
    const refused = failed(409, LAST_ADMIN)
    ;(api.patch as Mock).mockRejectedValue(refused)
    ;(api.del as Mock).mockRejectedValue(refused)
    await expect(changeMemberRole(ANNA.id, 'member')).rejects.toMatchObject({ detail: LAST_ADMIN })
    await expect(removeMember(ANNA.id)).rejects.toMatchObject({ detail: LAST_ADMIN })
  })

  it('removes a member with DELETE', async () => {
    ;(api.del as Mock).mockResolvedValue(undefined)
    await expect(removeMember(LUCA.id)).resolves.toBeUndefined()
    expect(api.del).toHaveBeenCalledWith(`/api/v1/auth/members/${LUCA.id}`)
  })

  it('tells a 404 from other failures', () => {
    expect(isNotFound(failed(404, 'Membro non trovato.'))).toBe(true)
    expect(isNotFound(failed(409, LAST_ADMIN))).toBe(false)
    expect(isNotFound(new Error('404'))).toBe(false)
  })

  it('names the state of an account and the person', () => {
    const base = normalizeMember(ANNA)
    expect(memberState(base)).toBe('active')
    expect(memberState({ ...base, email_verified: false })).toBe('unverified')
    expect(memberState({ ...base, is_active: false, email_verified: false })).toBe('inactive')
    expect(memberName(base)).toBe('Anna Rossi')
    expect(memberName({ ...base, name: '  ' })).toBe('anna@studio.example')
  })
})

describe('members API client in the demo', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    auth.demo = true
    resetDemoMembers()
  })

  it('shows example members, the demo account first as admin, without calling the server', async () => {
    const members = await listMembers()
    expect(members.map((m) => m.role)).toEqual(['admin', 'member', 'viewer'])
    expect(members[0].id).toBe('demo-user-001')
    expect(members.every((m) => m.email.endsWith('.example'))).toBe(true)
    expect(api.get).not.toHaveBeenCalled()
  })

  it('keeps role changes and removals until the examples are reset', async () => {
    const [, second, third] = await listMembers()
    expect((await changeMemberRole(second.id, 'viewer')).role).toBe('viewer')
    await removeMember(third.id)

    const after = await listMembers()
    expect(after.map((m: Member) => [m.id, m.role])).toEqual([
      ['demo-user-001', 'admin'],
      [second.id, 'viewer'],
    ])
    expect(api.patch).not.toHaveBeenCalled()
    expect(api.del).not.toHaveBeenCalled()

    resetDemoMembers()
    expect(await listMembers()).toHaveLength(3)
  })

  it('hands out copies, so a caller cannot change the examples by mistake', async () => {
    const [first] = await listMembers()
    first.role = 'viewer'
    expect((await listMembers())[0].role).toBe('admin')
  })

  it('answers 404 for a member it does not have', async () => {
    const err = await changeMemberRole('nobody', 'member').catch((e: unknown) => e)
    expect(isNotFound(err)).toBe(true)
    await expect(removeMember('nobody')).rejects.toBeInstanceOf(ApiError)
  })
})
