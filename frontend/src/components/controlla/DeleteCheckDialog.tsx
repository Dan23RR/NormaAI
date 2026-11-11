'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { useToast } from '@/components/ui/Toast'
import { deleteCheck, forgetCheck } from './documents-api'
import { FailureMessage } from './FailureMessage'
import { describeFailure, type Failure } from './errors'
import type { CheckSummary } from './types'

/** Confirmation before a check is deleted: it says what goes, and that the file was never kept. */
export function DeleteCheckDialog({
  open,
  onClose,
  check,
  onDeleted,
}: {
  open: boolean
  onClose: () => void
  check: Pick<CheckSummary, 'id' | 'filename'>
  onDeleted: (id: string) => void
}) {
  const t = useTranslations('controlla.remove')
  const { toast } = useToast()
  const [deleting, setDeleting] = useState(false)
  const [failure, setFailure] = useState<Failure | null>(null)

  const confirm = async () => {
    setDeleting(true)
    setFailure(null)
    try {
      await deleteCheck(check.id)
      forgetCheck(check.id)
      toast({ kind: 'ok', title: t('deletedTitle'), description: check.filename })
      onDeleted(check.id)
      onClose()
    } catch (err) {
      setFailure(describeFailure(err))
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
      <p className="break-words text-body text-ink">
        {t.rich('question', {
          name: check.filename,
          strong: (chunks) => <span className="font-medium">{chunks}</span>,
        })}
      </p>
      <p className="mt-2 text-small text-ink-2">{t('warning')}</p>
      {failure && <FailureMessage failure={failure} className="mt-3" />}
    </Dialog>
  )
}
