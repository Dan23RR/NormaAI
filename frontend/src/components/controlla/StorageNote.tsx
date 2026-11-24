'use client'

import { useTranslations } from 'next-intl'
import { itemKeys } from '@/components/LegalLayout'
import { cn } from '@/lib/cn'

/**
 * The note in the margin of the form: the document is not stored, and this
 * is the list of what is. It repeats what the documents API keeps of a
 * check, nothing more and nothing less.
 */
export function StorageNote({ className }: { className?: string }) {
  const t = useTranslations('controlla.storage')
  return (
    <aside aria-labelledby="storage-note-heading" className={cn('min-w-0', className)}>
      <h2 id="storage-note-heading" className="text-h4">
        {t('title')}
      </h2>
      <p className="mt-2 text-small text-ink-2">{t('body')}</p>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-small text-ink-2">
        {itemKeys(t.raw('items')).map((key) => (
          <li key={key}>{t(`items.${key}`)}</li>
        ))}
      </ul>
      <p className="mt-2 text-small text-ink-2">{t('delete')}</p>
    </aside>
  )
}
