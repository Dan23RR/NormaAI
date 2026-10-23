import { Suspense } from 'react'
import type { Metadata } from 'next'
import { getTranslations } from 'next-intl/server'
import { ChiediPage } from '@/components/chiedi/ChiediPage'
import { Spinner } from '@/components/ui/Button'

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations('chiedi')
  return { title: t('title') }
}

// useSearchParams (the ?q= prefill) needs a Suspense boundary above it.
export default async function Page() {
  const t = await getTranslations('chiedi')
  return (
    <Suspense
      fallback={
        <div className="flex items-center gap-2 py-12 text-small text-ink-2" role="status" aria-label={t('loading')}>
          <Spinner className="h-4 w-4 text-union" />
          <span>{t('loading')}</span>
        </div>
      }
    >
      <ChiediPage />
    </Suspense>
  )
}
