'use client'

import { useCallback, useEffect, useState } from 'react'
import { useTranslations } from 'next-intl'
import { Trash2 } from 'lucide-react'
import { Badge, Button, Dialog, Select, Skeleton, TBody, TD, TH, THead, TR, Table, useToast } from '@/components/ui'
import { InvitesSection } from '@/components/admin/InvitesSection'
import { useAuth } from '@/hooks/useAuth'
import { useErrorText } from '@/i18n/errors'
import type { User } from '@/lib/types'
import {
  MEMBER_ROLES,
  MEMBER_STATE_TONE,
  changeMemberRole,
  isMembersUnavailable,
  isNotFound,
  listMembers,
  memberName,
  memberState,
  removeMember,
  type Member,
  type MemberRole,
} from './members-api'
import { SettingsSection } from './SettingsSection'

type ListState =
  | { status: 'loading' }
  | { status: 'unavailable'; message: string }
  | { status: 'error'; message: string }
  | { status: 'ready'; members: Member[] }

/** An email that a narrow cell breaks after the @, not in the middle of a word. */
function Email({ value }: { value: string }) {
  const at = value.indexOf('@')
  if (at < 0) return <>{value}</>
  return (
    <>
      {value.slice(0, at + 1)}
      <wbr />
      {value.slice(at + 1)}
    </>
  )
}

/**
 * The organisation's members. An admin sees who they are, their role and the
 * state of their account, changes a role, removes someone and invites a new
 * person (the invitations of the Administration page). The API shows the
 * members to admins only, so the other roles get a note instead.
 */
export function MembersSection({ user, demoMode }: { user: User; demoMode: boolean }) {
  const t = useTranslations('impostazioni.members')
  const tRoot = useTranslations()
  // Set when the admin gives up the role here: the note replaces the list at
  // once, before the account is read again.
  const [steppedDown, setSteppedDown] = useState(false)
  const isAdmin = user.role === 'admin' && !steppedDown

  return (
    <SettingsSection id="membri" title={t('title')} description={t('description')}>
      {isAdmin ? (
        <div className="space-y-10">
          <MembersManager user={user} demoMode={demoMode} onSteppedDown={() => setSteppedDown(true)} />
          <div>
            <h3 className="text-h4">{t('invitesTitle')}</h3>
            <p className="mt-1 max-w-prose text-small text-ink-2">{tRoot('admin.invites.description')}</p>
            <div className="mt-4">
              <InvitesSection demoMode={demoMode} />
            </div>
          </div>
        </div>
      ) : (
        <p className="max-w-prose rounded-lg border border-rule bg-surface p-5 text-body text-ink-2">{t('adminOnly')}</p>
      )}
    </SettingsSection>
  )
}

function MembersManager({
  user,
  demoMode,
  onSteppedDown,
}: {
  user: User
  demoMode: boolean
  onSteppedDown: () => void
}) {
  const t = useTranslations('impostazioni.members')
  const tRoot = useTranslations()
  const errorText = useErrorText()
  const { toast } = useToast()
  const { refreshUser } = useAuth()
  const [list, setList] = useState<ListState>({ status: 'loading' })
  const [saving, setSaving] = useState<{ id: string; role: MemberRole } | null>(null)
  const [actionError, setActionError] = useState<{ title: string; message: string } | null>(null)
  const [stepDownRole, setStepDownRole] = useState<MemberRole | null>(null)
  const [stepDownError, setStepDownError] = useState<string | null>(null)
  const [removing, setRemoving] = useState<Member | null>(null)
  const [removeBusy, setRemoveBusy] = useState(false)
  const [removeError, setRemoveError] = useState<string | null>(null)

  const roleLabel = (role: MemberRole) => tRoot(`impostazioni.profile.roles.${role}`)
  const bold = (chunks: React.ReactNode) => <strong>{chunks}</strong>

  const load = useCallback(async () => {
    setList({ status: 'loading' })
    try {
      setList({ status: 'ready', members: await listMembers() })
    } catch (err) {
      if (isMembersUnavailable(err)) setList({ status: 'unavailable', message: errorText(err) })
      else setList({ status: 'error', message: errorText(err, 'errors.loadFailed') })
    }
  }, [errorText])

  useEffect(() => {
    load()
  }, [load])

  const replace = (updated: Member) =>
    setList((prev) =>
      prev.status === 'ready' ? { ...prev, members: prev.members.map((m) => (m.id === updated.id ? updated : m)) } : prev,
    )
  // A member the server no longer has (404) leaves the list as well.
  const drop = (id: string) =>
    setList((prev) => (prev.status === 'ready' ? { ...prev, members: prev.members.filter((m) => m.id !== id) } : prev))

  const me = list.status === 'ready' ? list.members.find((m) => m.id === user.id) : undefined

  /** Saves a role; throws what the API said, for the caller to show where the person is looking. */
  const saveRole = async (member: Member, role: MemberRole): Promise<Member> => {
    setSaving({ id: member.id, role })
    try {
      const updated = await changeMemberRole(member.id, role)
      replace(updated)
      return updated
    } finally {
      setSaving(null)
    }
  }

  const pickRole = async (member: Member, role: MemberRole) => {
    if (role === member.role) return
    setActionError(null)
    if (member.id === user.id && member.role === 'admin') {
      setStepDownError(null)
      setStepDownRole(role)
      return
    }
    try {
      const updated = await saveRole(member, role)
      toast({
        kind: 'ok',
        title: t('roleChangedTitle'),
        description: t('roleChangedDescription', { name: memberName(updated), role: roleLabel(updated.role) }),
      })
    } catch (err) {
      setActionError({
        title: t('roleFailedTitle', { name: memberName(member) }),
        message: errorText(err, 'impostazioni.members.roleFailed'),
      })
      if (isNotFound(err)) drop(member.id)
    }
  }

  const confirmStepDown = async () => {
    if (!me || !stepDownRole) return
    setStepDownError(null)
    try {
      const updated = await saveRole(me, stepDownRole)
      setStepDownRole(null)
      toast({ kind: 'ok', title: t('steppedDownTitle', { role: roleLabel(updated.role) }) })
      onSteppedDown()
      void refreshUser()
    } catch (err) {
      // The last active admin is refused here, with the server's reason.
      setStepDownError(errorText(err, 'impostazioni.members.roleFailed'))
    }
  }

  const askRemove = (member: Member) => {
    setActionError(null)
    setRemoveError(null)
    setRemoving(member)
  }

  const confirmRemove = async () => {
    if (!removing) return
    setRemoveBusy(true)
    setRemoveError(null)
    try {
      await removeMember(removing.id)
      drop(removing.id)
      toast({ kind: 'ok', title: t('removedTitle'), description: t('removedDescription', { name: memberName(removing) }) })
      setRemoving(null)
    } catch (err) {
      setRemoveError(errorText(err, 'impostazioni.members.removeFailed'))
      if (isNotFound(err)) drop(removing.id)
    } finally {
      setRemoveBusy(false)
    }
  }

  const stepDownBusy = saving !== null && saving.id === user.id

  let content: React.ReactNode
  if (list.status === 'loading') {
    content = (
      <div className="space-y-2" role="status" aria-label={t('loading')}>
        <Skeleton className="h-10" label={t('loading')} />
        <Skeleton className="h-12" label={t('loading')} />
      </div>
    )
  } else if (list.status === 'unavailable') {
    content = (
      <div role="status" className="rounded-lg border border-warn/40 bg-surface p-5">
        <h3 className="text-h4">{t('unavailableTitle')}</h3>
        <p className="mt-1 max-w-prose text-body text-ink-2">{list.message}</p>
      </div>
    )
  } else if (list.status === 'error') {
    content = (
      <div role="alert" className="rounded-lg border border-bad/30 bg-surface p-5">
        <h3 className="text-h4">{t('loadFailedTitle')}</h3>
        <p className="mt-1 text-body text-ink-2">{list.message}</p>
        <Button variant="secondary" className="mt-4" onClick={load}>
          {tRoot('ui.retryLoad')}
        </Button>
      </div>
    )
  } else {
    content = (
      <div className="space-y-4">
        {demoMode && <p className="max-w-prose text-small text-ink-2">{t('demoNote')}</p>}

        {actionError && (
          <div role="alert" className="rounded-lg border border-bad/30 bg-surface p-4">
            <p className="text-body font-medium text-ink">{actionError.title}</p>
            <p className="mt-1 text-small text-ink-2">{actionError.message}</p>
          </div>
        )}

        {list.members.length === 0 ? (
          <p className="text-body text-ink-2">{t('empty')}</p>
        ) : (
          <Table aria-label={t('title')}>
            <THead>
              <TR>
                <TH>{t('colPerson')}</TH>
                <TH>{t('colRole')}</TH>
                <TH>{t('colStatus')}</TH>
                <TH>
                  <span className="sr-only">{t('colActions')}</span>
                </TH>
              </TR>
            </THead>
            <TBody>
              {list.members.map((member) => {
                const own = member.id === user.id
                const name = memberName(member)
                const state = memberState(member)
                const busy = saving !== null && saving.id === member.id
                return (
                  <TR key={member.id}>
                    <TD>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="break-words font-medium">{name === member.email ? <Email value={name} /> : name}</span>
                        {own && <Badge tone="union">{t('you')}</Badge>}
                      </div>
                      {name !== member.email && (
                        <div className="break-words text-small text-ink-2">
                          <Email value={member.email} />
                        </div>
                      )}
                    </TD>
                    <TD>
                      <Select
                        aria-label={t('roleOf', { name })}
                        value={busy && saving ? saving.role : member.role}
                        onChange={(e) => pickRole(member, e.target.value as MemberRole)}
                        disabled={busy || (demoMode && own)}
                        aria-busy={busy || undefined}
                        // The longest role, Amministratore, with the arrow.
                        className="min-w-[10.5rem]"
                      >
                        {MEMBER_ROLES.map((role) => (
                          <option key={role} value={role}>
                            {roleLabel(role)}
                          </option>
                        ))}
                      </Select>
                      {busy && (
                        <span role="status" className="sr-only">
                          {t('saving')}
                        </span>
                      )}
                    </TD>
                    <TD>
                      <Badge tone={MEMBER_STATE_TONE[state]}>{t(`status.${state}`)}</Badge>
                    </TD>
                    <TD className="text-right">
                      {!own && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => askRemove(member)}
                          disabled={busy}
                          aria-label={t('removeLabel', { name })}
                          iconLeft={<Trash2 className="h-4 w-4" aria-hidden="true" />}
                        >
                          {t('remove')}
                        </Button>
                      )}
                    </TD>
                  </TR>
                )
              })}
            </TBody>
          </Table>
        )}

        <p className="max-w-prose text-caption text-ink-3">{t('ownAccount')}</p>

        <div>
          <h3 className="text-small font-medium text-ink">{t('rolesTitle')}</h3>
          <dl className="mt-2 space-y-1.5 text-small text-ink-2">
            {MEMBER_ROLES.map((role) => (
              <div key={role} className="sm:flex sm:gap-2">
                <dt className="shrink-0 font-medium text-ink sm:w-36">{roleLabel(role)}</dt>
                <dd>{t(`rolesHelp.${role}`)}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    )
  }

  return (
    <>
      {content}

      <Dialog
        open={stepDownRole !== null}
        onClose={() => {
          if (!stepDownBusy) setStepDownRole(null)
        }}
        title={t('stepDownTitle')}
        footer={
          <>
            <Button variant="secondary" onClick={() => setStepDownRole(null)} disabled={stepDownBusy}>
              {tRoot('ui.cancel')}
            </Button>
            <Button variant="danger" onClick={confirmStepDown} loading={stepDownBusy}>
              {t('stepDownConfirm')}
            </Button>
          </>
        }
      >
        {stepDownRole && <p className="text-body text-ink">{t('stepDownBody', { role: roleLabel(stepDownRole) })}</p>}
        {stepDownError && (
          <p role="alert" className="mt-3 text-small text-bad">
            {stepDownError}
          </p>
        )}
      </Dialog>

      <Dialog
        open={removing !== null}
        onClose={() => {
          if (!removeBusy) setRemoving(null)
        }}
        title={removing ? t('removeTitle', { name: memberName(removing) }) : t('remove')}
        description={removing?.email}
        footer={
          <>
            <Button variant="secondary" onClick={() => setRemoving(null)} disabled={removeBusy}>
              {tRoot('ui.cancel')}
            </Button>
            <Button variant="danger" onClick={confirmRemove} loading={removeBusy}>
              {t('removeConfirm')}
            </Button>
          </>
        }
      >
        <div className="space-y-2 text-body text-ink">
          <p>{t.rich('removeLost', { b: bold })}</p>
          <p>{t.rich('removeKept', { b: bold })}</p>
          <p className="text-small text-ink-2">{t('removeFinal')}</p>
        </div>
        {removeError && (
          <p role="alert" className="mt-3 text-small text-bad">
            {removeError}
          </p>
        )}
      </Dialog>
    </>
  )
}
