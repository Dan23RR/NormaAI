'use client'

import { useTranslations } from 'next-intl'
import { PageHeader } from '@/components/ui'
import { useAuth } from '@/hooks/useAuth'
import { DataSection } from '@/components/impostazioni/DataSection'
import { DemoSection } from '@/components/impostazioni/DemoSection'
import { LanguageSection } from '@/components/impostazioni/LanguageSection'
import { ProfileSection } from '@/components/impostazioni/ProfileSection'
import { ThemeSection } from '@/components/impostazioni/ThemeSection'

export default function ImpostazioniPage() {
  const t = useTranslations('impostazioni')
  const { user, demoMode } = useAuth()
  if (!user) return null

  return (
    <div>
      <PageHeader title={t('title')} description={t('description')} />
      <ProfileSection user={user} />
      <LanguageSection />
      <ThemeSection />
      <DataSection user={user} demoMode={demoMode} />
      {demoMode && <DemoSection />}
    </div>
  )
}
