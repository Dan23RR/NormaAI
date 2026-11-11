import { Suspense } from 'react'
import type { Metadata } from 'next'
import { getTranslations } from 'next-intl/server'
import { CheckDetailPage } from '@/components/controlla/CheckDetailPage'
import { Spinner } from '@/components/ui/Button'

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations('controlla')
  return { title: t('detailTitle') }
}

// The check is read in the browser (the session lives there): the page itself only frames it.
export default async function Page() {
  const t = await getTranslations('controlla')
  return (
    <Suspense
      fallback={
        <div className="flex items-center gap-2 py-12 text-small text-ink-2" role="status" aria-label={t('detail.loading')}>
          <Spinner className="h-4 w-4 text-union" />
          <span>{t('detail.loading')}</span>
        </div>
      }
    >
      <CheckDetailPage />
    </Suspense>
  )
}
