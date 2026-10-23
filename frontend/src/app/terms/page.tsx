import type { Metadata } from 'next'
import { getFormatter, getTranslations } from 'next-intl/server'
import { LEGAL_TAGS, LegalLayout, LegalSection, itemKeys } from '@/components/LegalLayout'
import { LONG_DATE } from '@/i18n/format'
import { LEGAL_UPDATED_ON } from '@/lib/legal-dates'

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations('legal.terms')
  return { title: t('title'), description: t('intro') }
}

export default async function TermsPage() {
  const t = await getTranslations('legal.terms')
  const format = await getFormatter()
  const rich = (key: string) => t.rich(key, LEGAL_TAGS)

  return (
    <LegalLayout title={t('title')} intro={t('intro')} lastUpdated={format.dateTime(LEGAL_UPDATED_ON, LONG_DATE)}>
      <LegalSection title={t('nature.title')}>
        {itemKeys(t.raw('nature.p')).map((k) => (
          <p key={k}>{rich(`nature.p.${k}`)}</p>
        ))}
      </LegalSection>

      <LegalSection title={t('ai.title')}>
        <p>{t('ai.intro')}</p>
        <ul>
          {itemKeys(t.raw('ai.items')).map((k) => (
            <li key={k}>{rich(`ai.items.${k}`)}</li>
          ))}
        </ul>
        <p>{t('ai.p')}</p>
      </LegalSection>

      <LegalSection title={t('liability.title')}>
        {itemKeys(t.raw('liability.p')).map((k) => (
          <p key={k}>{rich(`liability.p.${k}`)}</p>
        ))}
      </LegalSection>

      <LegalSection title={t('warranty.title')}>
        <p>{t('warranty.p')}</p>
      </LegalSection>

      <LegalSection title={t('updates.title')}>
        <p>{t('updates.p')}</p>
      </LegalSection>

      <LegalSection title={t('data.title')}>
        <p>{rich('data.p')}</p>
      </LegalSection>

      <LegalSection title={t('source.title')}>
        <p>{rich('source.p')}</p>
      </LegalSection>

      <LegalSection title={t('changes.title')}>
        <p>{t('changes.p')}</p>
      </LegalSection>
    </LegalLayout>
  )
}
