'use client'

import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { useTranslations } from 'next-intl'
import { Copy, MailPlus } from 'lucide-react'
import { Badge, Button, EmptyState, Field, Input, Select, Skeleton, TBody, TD, TH, THead, TR, Table, useToast } from '@/components/ui'
import { formatIsoDate, formatIsoDateTime } from '@/components/clienti/format'
import { useErrorText } from '@/i18n/errors'
import {
  INVITE_ROLES,
  createInvite,
  inviteRoleLabel,
  inviteStatus,
  isInvitesUnavailable,
  listInvites,
  validateInviteEmail,
  type CreatedInvite,
  type Invite,
  type InviteRole,
} from './invites-api'

type ListState =
  | { status: 'loading' }
  | { status: 'unavailable'; message: string }
  | { status: 'error'; message: string }
  | { status: 'ready'; invites: Invite[] }

/** Create invitation codes and see the ones issued so far. */
export function InvitesSection({ demoMode }: { demoMode: boolean }) {
  const t = useTranslations('admin.invites')
  const tRoot = useTranslations()
  const errorText = useErrorText()
  const { toast } = useToast()
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<InviteRole>('member')
  const [emailError, setEmailError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [created, setCreated] = useState<CreatedInvite | null>(null)
  const [list, setList] = useState<ListState>({ status: 'loading' })
  const missing = tRoot('ui.notAvailable')

  const load = useCallback(async () => {
    setList({ status: 'loading' })
    try {
      setList({ status: 'ready', invites: await listInvites() })
    } catch (err) {
      if (isInvitesUnavailable(err)) setList({ status: 'unavailable', message: errorText(err) })
      else setList({ status: 'error', message: errorText(err, 'errors.loadFailed') })
    }
  }, [errorText])

  useEffect(() => {
    load()
  }, [load])

  const copy = async (code: string) => {
    try {
      await navigator.clipboard.writeText(code)
      toast({ kind: 'ok', title: t('copiedTitle'), description: code })
    } catch {
      toast({ kind: 'bad', title: t('copyFailed'), description: t('copyFailedDescription') })
    }
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const problem = validateInviteEmail(email)
    setEmailError(problem ? t(`errors.${problem}`) : null)
    if (problem) {
      document.getElementById('invite-email')?.focus()
      return
    }
    setCreating(true)
    setCreateError(null)
    try {
      const invite = await createInvite(email.trim(), role)
      setCreated(invite)
      setEmail('')
      toast({ kind: 'ok', title: t('createdTitle'), description: invite.email })
      load()
    } catch (err) {
      if (isInvitesUnavailable(err)) {
        const message = errorText(err)
        setList({ status: 'unavailable', message })
        setCreateError(message)
      } else {
        setCreateError(errorText(err, 'admin.invites.createFailed'))
      }
    } finally {
      setCreating(false)
    }
  }

  const unavailable = list.status === 'unavailable'

  return (
    <div className="space-y-6">
      {demoMode && <p className="text-small text-ink-2">{t('demoNote')}</p>}

      {unavailable ? (
        <div role="status" className="rounded-lg border border-warn/40 bg-surface p-5">
          <h3 className="text-h4">{t('unavailableTitle')}</h3>
          <p className="mt-1 max-w-prose text-body text-ink-2">{list.message}</p>
          <p className="mt-2 max-w-prose text-small text-ink-2">{t('unavailableBody')}</p>
        </div>
      ) : (
        <form onSubmit={submit} noValidate className="rounded-lg border border-rule bg-surface p-5">
          <h3 className="text-h4">{t('createTitle')}</h3>
          <p className="mt-1 max-w-prose text-small text-ink-2">{t('createLead')}</p>
          <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-start">
            <Field label={t('email')} htmlFor="invite-email" required error={emailError ?? undefined} className="w-full sm:max-w-sm">
              <Input
                id="invite-email"
                type="email"
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value)
                  if (emailError) setEmailError(null)
                }}
                placeholder={t('emailPlaceholder')}
                autoComplete="off"
                disabled={creating}
                invalid={!!emailError}
                aria-describedby={emailError ? 'invite-email-error' : undefined}
              />
            </Field>
            <Field label={t('role')} htmlFor="invite-role" help={t('roleHelp')} className="w-full sm:max-w-[200px]">
              <Select
                id="invite-role"
                value={role}
                onChange={(e) => setRole(e.target.value as InviteRole)}
                disabled={creating}
                aria-describedby="invite-role-help"
              >
                {INVITE_ROLES.map((r) => (
                  <option key={r} value={r}>
                    {inviteRoleLabel(r, tRoot)}
                  </option>
                ))}
              </Select>
            </Field>
            <Button
              type="submit"
              loading={creating}
              className="sm:mt-[26px]"
              iconLeft={<MailPlus className="h-4 w-4" aria-hidden="true" />}
            >
              {t('create')}
            </Button>
          </div>
          {createError && (
            <p role="alert" className="mt-3 text-small text-bad">
              {createError}
            </p>
          )}
        </form>
      )}

      {created && (
        <div role="status" className="rounded-lg border border-ok/30 bg-surface p-5">
          <h3 className="text-h4">{t('createdFor', { email: created.email })}</h3>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <code className="rounded-md bg-surface-2 px-3 py-2 font-mono text-h4 text-ink">{created.code}</code>
            <Button variant="secondary" size="sm" onClick={() => copy(created.code)} iconLeft={<Copy className="h-4 w-4" aria-hidden="true" />}>
              {t('copyCode')}
            </Button>
          </div>
          <p className="mt-2 text-small text-ink-2">
            {t.rich('expires', {
              date: formatIsoDateTime(created.expires_at) ?? missing,
              num: (chunks) => <span className="tabular">{chunks}</span>,
            })}
          </p>
        </div>
      )}

      {list.status === 'loading' && (
        <div className="space-y-2" role="status" aria-label={t('loading')}>
          <Skeleton className="h-10" label={t('loading')} />
          <Skeleton className="h-12" label={t('loading')} />
        </div>
      )}

      {list.status === 'error' && (
        <div role="alert" className="rounded-lg border border-bad/30 bg-surface p-5">
          <h3 className="text-h4">{t('loadFailedTitle')}</h3>
          <p className="mt-1 text-body text-ink-2">{list.message}</p>
          <Button variant="secondary" className="mt-4" onClick={load}>
            {tRoot('ui.retryLoad')}
          </Button>
        </div>
      )}

      {list.status === 'ready' && list.invites.length === 0 && (
        <EmptyState title={t('emptyTitle')} description={t('emptyDescription')} />
      )}

      {list.status === 'ready' && list.invites.length > 0 && (
        <Table>
          <THead>
            <TR>
              <TH>{t('colEmail')}</TH>
              <TH>{t('colRole')}</TH>
              <TH>{t('colStatus')}</TH>
              <TH className="hidden md:table-cell">{t('colCreated')}</TH>
              <TH className="hidden sm:table-cell">{t('colExpires')}</TH>
            </TR>
          </THead>
          <TBody>
            {list.invites.map((invite) => {
              const status = inviteStatus(invite, tRoot)
              return (
                <TR key={invite.id || `${invite.email}-${invite.created_at}`}>
                  <TD className="font-medium">{invite.email}</TD>
                  <TD className="text-ink-2">{inviteRoleLabel(invite.role, tRoot)}</TD>
                  <TD>
                    <Badge tone={status.tone}>{status.label}</Badge>
                  </TD>
                  <TD className="hidden tabular text-ink-2 md:table-cell">{formatIsoDate(invite.created_at) ?? missing}</TD>
                  <TD className="hidden tabular text-ink-2 sm:table-cell">{formatIsoDate(invite.expires_at) ?? missing}</TD>
                </TR>
              )
            })}
          </TBody>
        </Table>
      )}
    </div>
  )
}
