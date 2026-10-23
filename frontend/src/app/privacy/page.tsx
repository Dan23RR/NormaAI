import type { Metadata } from 'next'
import { getFormatter, getTranslations } from 'next-intl/server'
import { LEGAL_TAGS, LegalLayout, LegalSection, itemKeys } from '@/components/LegalLayout'
import { LONG_DATE } from '@/i18n/format'
import { LEGAL_UPDATED_ON } from '@/lib/legal-dates'

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations('legal.privacy')
  return { title: t('title'), description: t('intro') }
}

export default async function PrivacyPage() {
  const t = await getTranslations('legal.privacy')
  const format = await getFormatter()
  const rich = (key: string) => t.rich(key, LEGAL_TAGS)
  const list = (key: string) => (
    <ul>
      {itemKeys(t.raw(key)).map((k) => (
        <li key={k}>{rich(`${key}.${k}`)}</li>
      ))}
    </ul>
  )

  return (
    <LegalLayout title={t('title')} intro={t('intro')} lastUpdated={format.dateTime(LEGAL_UPDATED_ON, LONG_DATE)}>
      <LegalSection title={t('owner.title')}>
        {itemKeys(t.raw('owner.p')).map((k) => (
          <p key={k}>{rich(`owner.p.${k}`)}</p>
        ))}
      </LegalSection>

      <LegalSection title={t('data.title')}>
        <p>{t('data.intro1')}</p>
        {list('data.app')}
        <p>{t('data.intro2')}</p>
        {list('data.site')}
      </LegalSection>

      <LegalSection title={t('basis.title')}>
        {list('basis.items')}
        <p>{t('basis.p')}</p>
      </LegalSection>

      <LegalSection title={t('processors.title')}>
        {list('processors.items')}
        <p>{t('processors.p')}</p>
      </LegalSection>

      <LegalSection title={t('retention.title')}>{list('retention.items')}</LegalSection>

      <LegalSection title={t('rights.title')}>
        {itemKeys(t.raw('rights.p')).map((k) => (
          <p key={k}>{rich(`rights.p.${k}`)}</p>
        ))}
      </LegalSection>

      <LegalSection title={t('ai.title')}>
        {itemKeys(t.raw('ai.p')).map((k) => (
          <p key={k}>{rich(`ai.p.${k}`)}</p>
        ))}
      </LegalSection>

      <LegalSection title={t('security.title')}>
        <p>{rich('security.p')}</p>
      </LegalSection>

      <LegalSection title={t('changes.title')}>
        <p>{t('changes.p')}</p>
      </LegalSection>
    </LegalLayout>
  )
}
