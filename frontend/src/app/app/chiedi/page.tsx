import { Suspense } from 'react'
import type { Metadata } from 'next'
import { ChiediPage } from '@/components/chiedi/ChiediPage'
import { Spinner } from '@/components/ui/Button'

export const metadata: Metadata = {
  title: 'Chiedi',
}

// useSearchParams (the ?q= prefill) needs a Suspense boundary above it.
export default function Page() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center gap-2 py-12 text-small text-ink-2" role="status" aria-label="Caricamento">
          <Spinner className="h-4 w-4 text-union" />
          <span>Caricamento</span>
        </div>
      }
    >
      <ChiediPage />
    </Suspense>
  )
}
