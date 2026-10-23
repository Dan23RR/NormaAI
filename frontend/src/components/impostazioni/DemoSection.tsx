'use client'

import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { LogOut } from 'lucide-react'
import { Button } from '@/components/ui'
import { useAuth } from '@/hooks/useAuth'
import { SettingsSection } from './SettingsSection'

/** Shown only in the demo: what it is, what it is not, how to leave it. */
export function DemoSection() {
  const t = useTranslations('impostazioni.demo')
  const { logout } = useAuth()
  const router = useRouter()

  const leave = () => {
    logout()
    router.replace('/login')
  }

  return (
    <SettingsSection id="demo" title={t('title')} description={t('description')}>
      <div className="rounded-lg border border-mark-deep/40 bg-mark/20 p-5">
        <p className="max-w-prose text-body text-ink">{t('body')}</p>
        <Button className="mt-4" variant="secondary" onClick={leave} iconLeft={<LogOut className="h-4 w-4" aria-hidden="true" />}>
          {t('leave')}
        </Button>
      </div>
    </SettingsSection>
  )
}
