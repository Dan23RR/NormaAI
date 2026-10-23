'use client'

import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Copy, MailPlus } from 'lucide-react'
import { Badge, Button, EmptyState, Field, Input, Skeleton, TBody, TD, TH, THead, TR, Table, useToast } from '@/components/ui'
import { formatIsoDate, formatIsoDateTime } from '@/components/clienti/format'
import {
  InvitesUnavailableError,
  createInvite,
  inviteStatus,
  listInvites,
  validateInviteEmail,
  type CreatedInvite,
  type Invite,
} from './invites-api'

type ListState =
  | { status: 'loading' }
  | { status: 'unavailable'; message: string }
  | { status: 'error'; message: string }
  | { status: 'ready'; invites: Invite[] }

/** Create invitation codes and see the ones issued so far. */
export function InvitesSection({ demoMode }: { demoMode: boolean }) {
  const { toast } = useToast()
  const [email, setEmail] = useState('')
  const [emailError, setEmailError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [created, setCreated] = useState<CreatedInvite | null>(null)
  const [list, setList] = useState<ListState>({ status: 'loading' })

  const load = useCallback(async () => {
    setList({ status: 'loading' })
    try {
      setList({ status: 'ready', invites: await listInvites() })
    } catch (err) {
      if (err instanceof InvitesUnavailableError) setList({ status: 'unavailable', message: err.message })
      else setList({ status: 'error', message: err instanceof Error ? err.message : 'Caricamento non riuscito.' })
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const copy = async (code: string) => {
    try {
      await navigator.clipboard.writeText(code)
      toast({ kind: 'ok', title: 'Codice copiato', description: code })
    } catch {
      toast({ kind: 'bad', title: 'Copia non riuscita', description: 'Seleziona il codice e copialo a mano.' })
    }
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const problem = validateInviteEmail(email)
    setEmailError(problem)
    if (problem) {
      document.getElementById('invite-email')?.focus()
      return
    }
    setCreating(true)
    setCreateError(null)
    try {
      const invite = await createInvite(email.trim())
      setCreated(invite)
      setEmail('')
      toast({ kind: 'ok', title: 'Invito creato', description: invite.email })
      load()
    } catch (err) {
      if (err instanceof InvitesUnavailableError) {
        setList({ status: 'unavailable', message: err.message })
        setCreateError(err.message)
      } else {
        setCreateError(err instanceof Error ? err.message : 'Creazione non riuscita. Riprova.')
      }
    } finally {
      setCreating(false)
    }
  }

  const unavailable = list.status === 'unavailable'

  return (
    <div className="space-y-6">
      {demoMode && (
        <p className="text-small text-ink-2">Nella demo gli inviti restano in questa sessione del browser.</p>
      )}

      {unavailable ? (
        <div role="status" className="rounded-lg border border-warn/40 bg-surface p-5">
          <h3 className="text-h4">Gli inviti non sono ancora attivi su questo server</h3>
          <p className="mt-1 max-w-prose text-body text-ink-2">{list.message}</p>
          <p className="mt-2 max-w-prose text-small text-ink-2">
            Quando il backend verrà aggiornato, da qui potrai creare i codici per far entrare nuove persone
            nell’organizzazione. Nel frattempo scrivi a info@normaai.org.
          </p>
        </div>
      ) : (
        <form onSubmit={submit} noValidate className="rounded-lg border border-rule bg-surface p-5">
          <h3 className="text-h4">Invita una persona</h3>
          <p className="mt-1 max-w-prose text-small text-ink-2">
            Il codice va inserito al momento della registrazione e vale una volta sola.
          </p>
          <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-start">
            <Field label="Email" htmlFor="invite-email" required error={emailError ?? undefined} className="w-full sm:max-w-sm">
              <Input
                id="invite-email"
                type="email"
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value)
                  if (emailError) setEmailError(null)
                }}
                placeholder="nome@azienda.it"
                autoComplete="off"
                disabled={creating}
                invalid={!!emailError}
                aria-describedby={emailError ? 'invite-email-error' : undefined}
              />
            </Field>
            <Button
              type="submit"
              loading={creating}
              className="sm:mt-[26px]"
              iconLeft={<MailPlus className="h-4 w-4" aria-hidden="true" />}
            >
              Crea l’invito
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
          <h3 className="text-h4">Invito creato per {created.email}</h3>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <code className="rounded-md bg-surface-2 px-3 py-2 font-mono text-h4 text-ink">{created.code}</code>
            <Button variant="secondary" size="sm" onClick={() => copy(created.code)} iconLeft={<Copy className="h-4 w-4" aria-hidden="true" />}>
              Copia il codice
            </Button>
          </div>
          <p className="mt-2 text-small text-ink-2">
            Scade il <span className="tabular">{formatIsoDateTime(created.expires_at) ?? 'n.d.'}</span>. Invialo tu alla
            persona: il server non manda email.
          </p>
        </div>
      )}

      {list.status === 'loading' && (
        <div className="space-y-2" role="status" aria-label="Caricamento degli inviti">
          <Skeleton className="h-10" label="Caricamento degli inviti" />
          <Skeleton className="h-12" label="Caricamento degli inviti" />
        </div>
      )}

      {list.status === 'error' && (
        <div role="alert" className="rounded-lg border border-bad/30 bg-surface p-5">
          <h3 className="text-h4">Gli inviti non si sono caricati</h3>
          <p className="mt-1 text-body text-ink-2">{list.message}</p>
          <Button variant="secondary" className="mt-4" onClick={load}>
            Riprova il caricamento
          </Button>
        </div>
      )}

      {list.status === 'ready' && list.invites.length === 0 && (
        <EmptyState
          title="Nessun invito ancora"
          description="Crea il primo codice qui sopra e invialo alla persona che vuoi far entrare."
        />
      )}

      {list.status === 'ready' && list.invites.length > 0 && (
        <Table>
          <THead>
            <TR>
              <TH>Email</TH>
              <TH>Codice</TH>
              <TH>Stato</TH>
              <TH className="hidden md:table-cell">Creato</TH>
              <TH className="hidden sm:table-cell">Scade</TH>
              <TH>
                <span className="sr-only">Azioni</span>
              </TH>
            </TR>
          </THead>
          <TBody>
            {list.invites.map((invite) => {
              const status = inviteStatus(invite)
              return (
                <TR key={`${invite.code}-${invite.email}`}>
                  <TD className="font-medium">{invite.email}</TD>
                  <TD>
                    <code className="font-mono text-small">{invite.code}</code>
                  </TD>
                  <TD>
                    <Badge tone={status.tone}>{status.label}</Badge>
                  </TD>
                  <TD className="hidden tabular text-ink-2 md:table-cell">{formatIsoDate(invite.created_at) ?? 'n.d.'}</TD>
                  <TD className="hidden tabular text-ink-2 sm:table-cell">{formatIsoDate(invite.expires_at) ?? 'n.d.'}</TD>
                  <TD className="text-right">
                    <Button variant="ghost" size="sm" onClick={() => copy(invite.code)} iconLeft={<Copy className="h-4 w-4" aria-hidden="true" />}>
                      Copia il codice
                    </Button>
                  </TD>
                </TR>
              )
            })}
          </TBody>
        </Table>
      )}
    </div>
  )
}
