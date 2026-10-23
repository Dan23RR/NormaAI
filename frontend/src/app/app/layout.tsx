'use client'

import { useEffect } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { useAuth } from '@/hooks/useAuth'
import { AppShell } from '@/components/app/AppShell'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { Spinner } from '@/components/ui/Button'

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const t = useTranslations('app.shell')
  const { user, loading } = useAuth()
  const router = useRouter()
  const pathname = usePathname()

  useEffect(() => {
    if (!loading && !user) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`)
    }
  }, [user, loading, router, pathname])

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-canvas" role="status" aria-label={t('loading')}>
        <Spinner className="h-6 w-6 text-union" />
        <span className="sr-only">{t('loading')}</span>
      </div>
    )
  }

  if (!user) return null

  return (
    <AppShell>
      <ErrorBoundary>{children}</ErrorBoundary>
    </AppShell>
  )
}
