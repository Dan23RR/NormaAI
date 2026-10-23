'use client'

import { useState } from 'react'
import { Download, Mail, Trash2 } from 'lucide-react'
import { Button, Dialog, Field, Input, buttonClasses, useToast } from '@/components/ui'
import { api } from '@/lib/api'
import { getAccessToken } from '@/lib/auth'
import type { User } from '@/lib/types'
import { formatIsoDate } from '@/components/clienti/format'
import { SettingsSection } from './SettingsSection'

/**
 * GDPR rights against src/api/routers/gdpr.py (both admin-only):
 * - GET  /api/v1/gdpr/export           -> JSON dump of the organization's data (3 per hour)
 * - POST /api/v1/gdpr/erase {confirm_org_id} -> deletes the organization's content, keeps users and org
 * Account closure has no endpoint yet: it goes by email.
 */

interface EraseResponse {
  status: string
  org_id: string
  deleted: Record<string, number>
}

/** The organization id is a claim of the access token (src/auth/security.py). */
function orgIdFromToken(): string | null {
  const token = getAccessToken()
  if (!token) return null
  try {
    const segment = token.split('.')[1] ?? ''
    const base64 = segment.replace(/-/g, '+').replace(/_/g, '/')
    const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4)
    const payload = JSON.parse(atob(padded)) as { org_id?: unknown }
    return typeof payload.org_id === 'string' ? payload.org_id : null
  } catch {
    return null
  }
}

const DELETED_LABEL: Record<string, string> = {
  clients: 'clienti',
  conversations: 'conversazioni',
  assessments: 'analisi',
  alerts: 'avvisi',
}

export function DataSection({ user, demoMode }: { user: User; demoMode: boolean }) {
  const { toast } = useToast()
  const isAdmin = user.role === 'admin'
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)
  const [eraseOpen, setEraseOpen] = useState(false)
  const [confirmName, setConfirmName] = useState('')
  const [erasing, setErasing] = useState(false)
  const [eraseError, setEraseError] = useState<string | null>(null)

  const exportData = async () => {
    setExporting(true)
    setExportError(null)
    try {
      const data = await api.get<unknown>('/api/v1/gdpr/export')
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const filename = `normaai-export-${formatIsoDate(new Date().toISOString())}.json`
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      toast({ kind: 'ok', title: 'Dati esportati', description: filename })
    } catch (err) {
      setExportError(err instanceof Error ? err.message : 'Esportazione non riuscita. Riprova.')
    } finally {
      setExporting(false)
    }
  }

  const orgId = orgIdFromToken()
  const nameMatches = confirmName.trim().toLowerCase() === (user.organization_name ?? '').trim().toLowerCase()

  const erase = async () => {
    if (!orgId) return
    setErasing(true)
    setEraseError(null)
    try {
      const res = await api.post<EraseResponse>('/api/v1/gdpr/erase', { confirm_org_id: orgId })
      const parts = Object.entries(res.deleted ?? {}).map(([k, v]) => `${v} ${DELETED_LABEL[k] ?? k}`)
      toast({ kind: 'ok', title: 'Dati dell’organizzazione cancellati', description: parts.join(', ') })
      setEraseOpen(false)
      setConfirmName('')
    } catch (err) {
      setEraseError(err instanceof Error ? err.message : 'Cancellazione non riuscita. Riprova.')
    } finally {
      setErasing(false)
    }
  }

  const mailto = `mailto:info@normaai.org?subject=${encodeURIComponent('Richiesta di cancellazione dell’account')}&body=${encodeURIComponent(
    `Chiedo la cancellazione dell’account ${user.email}` +
      (user.organization_name ? ` (organizzazione ${user.organization_name}).` : '.'),
  )}`

  return (
    <SettingsSection
      id="dati"
      title="I tuoi dati"
      description="Esportazione e cancellazione secondo il GDPR (artt. 15, 17 e 20 del Regolamento (UE) 2016/679)."
    >
      <div className="space-y-6">
        <div className="rounded-lg border border-rule bg-surface p-5">
          <h3 className="text-h4">Esporta i dati dell’organizzazione</h3>
          <p className="mt-1 max-w-prose text-small text-ink-2">
            Un file JSON con utenti, clienti, conversazioni, analisi e avvisi. Al massimo tre esportazioni all’ora.
          </p>
          {demoMode ? (
            <p className="mt-3 text-small text-ink-2">
              Nella demo con dati di esempio non c’è nulla di tuo da esportare: l’esportazione è disponibile con un account
              reale.
            </p>
          ) : !isAdmin ? (
            <p className="mt-3 text-small text-ink-2">
              L’esportazione è riservata agli amministratori dell’organizzazione: chiedi a loro, oppure scrivi a
              info@normaai.org.
            </p>
          ) : (
            <>
              <Button
                className="mt-4"
                variant="secondary"
                onClick={exportData}
                loading={exporting}
                iconLeft={<Download className="h-4 w-4" aria-hidden="true" />}
              >
                {exporting ? 'Preparazione del file' : 'Scarica i dati (JSON)'}
              </Button>
              {exportError && (
                <p role="alert" className="mt-3 text-small text-bad">
                  {exportError}
                </p>
              )}
            </>
          )}
        </div>

        {isAdmin && !demoMode && (
          <div className="rounded-lg border border-rule bg-surface p-5">
            <h3 className="text-h4">Cancella i dati dell’organizzazione</h3>
            <p className="mt-1 max-w-prose text-small text-ink-2">
              Elimina clienti, analisi, avvisi, conversazioni e i documenti caricati. Gli account e l’organizzazione
              restano, così puoi ripartire da zero. Non si può annullare.
            </p>
            {orgId ? (
              <Button
                className="mt-4"
                variant="danger"
                onClick={() => setEraseOpen(true)}
                iconLeft={<Trash2 className="h-4 w-4" aria-hidden="true" />}
              >
                Cancella i dati dell’organizzazione
              </Button>
            ) : (
              <p className="mt-3 text-small text-ink-2">
                La sessione non contiene l’identificativo dell’organizzazione: esci e accedi di nuovo per usare questa
                funzione.
              </p>
            )}
          </div>
        )}

        <div className="rounded-lg border border-rule bg-surface p-5">
          <h3 className="text-h4">Cancella l’account</h3>
          <p className="mt-1 max-w-prose text-small text-ink-2">
            La chiusura dell’account non è ancora automatica: la chiedi per email e la confermiamo entro 30 giorni, come
            prevede l’art. 12 del GDPR.
          </p>
          <a
            href={mailto}
            className={buttonClasses({ variant: 'secondary', className: 'mt-4' })}
          >
            <Mail className="h-4 w-4" aria-hidden="true" />
            Scrivi per cancellare l’account
          </a>
        </div>
      </div>

      <Dialog
        open={eraseOpen}
        onClose={() => {
          if (!erasing) setEraseOpen(false)
        }}
        title="Cancella i dati dell’organizzazione"
        description="Clienti, analisi, avvisi, conversazioni e documenti caricati vengono eliminati in modo definitivo."
        footer={
          <>
            <Button variant="secondary" onClick={() => setEraseOpen(false)} disabled={erasing}>
              Annulla
            </Button>
            <Button variant="danger" onClick={erase} loading={erasing} disabled={!nameMatches}>
              Cancella i dati dell’organizzazione
            </Button>
          </>
        }
      >
        <Field
          label={`Per confermare scrivi il nome dell’organizzazione: ${user.organization_name}`}
          htmlFor="erase-confirm"
          error={eraseError ?? undefined}
        >
          <Input
            id="erase-confirm"
            value={confirmName}
            onChange={(e) => setConfirmName(e.target.value)}
            autoComplete="off"
            disabled={erasing}
            invalid={!!eraseError}
          />
        </Field>
      </Dialog>
    </SettingsSection>
  )
}
