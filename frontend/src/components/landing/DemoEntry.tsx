'use client'

import Link from 'next/link'
import { useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { useAuth } from '@/hooks/useAuth'
import { Spinner } from '@/components/ui/Button'
import { getAccessToken, isDemoMode } from '@/lib/auth'
import { demoDestination } from './demo-entry'

/**
 * The /demo route: one step from the public site into the demo with sample
 * data. It turns demo mode on the way the button of the sign-in page does
 * (`loginDemo`), then moves to the first page of the demo.
 *
 * A session that is already signed in is left as it is: a link on the public
 * site must never sign anyone out, so that visitor simply lands in the
 * application.
 */
export function DemoEntry() {
  const t = useTranslations('landing.demoEntry')
  const { loginDemo } = useAuth()
  const router = useRouter()
  const destination = demoDestination()
  const opened = useRef(false)

  useEffect(() => {
    // Once per visit: `loginDemo` changes identity when the session changes.
    if (opened.current) return
    opened.current = true
    const signedIn = Boolean(getAccessToken()) && !isDemoMode()
    if (!signedIn) loginDemo()
    // replace, not push: "back" from the demo returns to the page before /demo.
    router.replace(destination)
  }, [loginDemo, router, destination])

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 bg-canvas px-6 text-center">
      <p role="status" className="flex items-center gap-3 text-read text-ink">
        <Spinner className="h-5 w-5 text-union" />
        {t('opening')}
      </p>
      <p className="text-small text-ink-2">
        {t.rich('fallback', {
          link: (chunks) => (
            <Link href={destination} className="text-union hover:underline">
              {chunks}
            </Link>
          ),
        })}
      </p>
    </main>
  )
}
