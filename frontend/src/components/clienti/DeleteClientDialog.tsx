'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { Button, Dialog, useToast } from '@/components/ui'
import { useErrorText } from '@/i18n/errors'
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
  const t = useTranslations('clienti.delete')
  const errorText = useErrorText()
  const { toast } = useToast()
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const confirm = async () => {
    if (!client) return
    setDeleting(true)
    setError(null)
    try {
      await deleteClient(client.id)
      toast({ kind: 'ok', title: t('deletedTitle'), description: client.name })
      onDeleted(client.id)
      onClose()
    } catch (err) {
      setError(errorText(err, 'clienti.delete.failed'))
    } finally {
      setDeleting(false)
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={t('title')}
      size="sm"
      footer={
        <>
          <Button type="button" variant="secondary" onClick={onClose} disabled={deleting}>
            {t('cancel')}
          </Button>
          <Button type="button" variant="danger" onClick={confirm} loading={deleting}>
            {t('confirm')}
          </Button>
        </>
      }
    >
      <p className="text-body text-ink">
        {t.rich('question', {
          name: client?.name ?? '',
          strong: (chunks) => <span className="font-medium">{chunks}</span>,
        })}
      </p>
      <p className="mt-2 text-small text-ink-2">{t('warning')}</p>
      {error && (
        <p role="alert" className="mt-3 rounded-md border border-bad/30 bg-bad/10 px-3 py-2 text-small text-bad">
          {error}
        </p>
      )}
    </Dialog>
  )
}
