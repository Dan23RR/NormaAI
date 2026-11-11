import { Suspense } from 'react'
import type { Metadata } from 'next'
import { getTranslations } from 'next-intl/server'
import { ControllaPage } from '@/components/controlla/ControllaPage'
import { Spinner } from '@/components/ui/Button'

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations('controlla')
  return { title: t('title') }
}

// useSearchParams (the ?cliente= preselection) needs a Suspense boundary above it.
export default async function Page() {
  const t = await getTranslations('controlla')
  return (
    <Suspense
      fallback={
        <div className="flex items-center gap-2 py-12 text-small text-ink-2" role="status" aria-label={t('loading')}>
          <Spinner className="h-4 w-4 text-union" />
          <span>{t('loading')}</span>
        </div>
      }
    >
      <ControllaPage />
    </Suspense>
  )
}
