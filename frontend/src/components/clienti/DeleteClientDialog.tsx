'use client'

import { useState } from 'react'
import { Button, Dialog, useToast } from '@/components/ui'
import type { Client } from '@/lib/types'
import { deleteClient } from './clients-api'

/** Confirmation before a deletion: the verb is the same on the button and in the title. */
export function DeleteClientDialog({
  open,
  onClose,
  client,
  onDeleted,
}: {
  open: boolean
  onClose: () => void
  client: Client | null
  onDeleted: (id: string) => void
}) {
  const { toast } = useToast()
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const confirm = async () => {
    if (!client) return
    setDeleting(true)
    setError(null)
    try {
      await deleteClient(client.id)
      toast({ kind: 'ok', title: 'Cliente eliminato', description: client.name })
      onDeleted(client.id)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Eliminazione non riuscita. Riprova.')
    } finally {
      setDeleting(false)
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Elimina il cliente"
      size="sm"
      footer={
        <>
          <Button type="button" variant="secondary" onClick={onClose} disabled={deleting}>
            Annulla
          </Button>
          <Button type="button" variant="danger" onClick={confirm} loading={deleting}>
            Elimina il cliente
          </Button>
        </>
      }
    >
      <p className="text-body text-ink">
        Vuoi eliminare <span className="font-medium">{client?.name}</span>?
      </p>
      <p className="mt-2 text-small text-ink-2">
        Vengono cancellate anche le analisi, gli avvisi e le conversazioni collegate. L&apos;operazione non si può
        annullare.
      </p>
      {error && (
        <p role="alert" className="mt-3 rounded-md border border-bad/30 bg-bad/10 px-3 py-2 text-small text-bad">
          {error}
        </p>
      )}
    </Dialog>
  )
}
