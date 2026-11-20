import type { Metadata } from 'next'
import { getFormatter, getTranslations } from 'next-intl/server'
import { LEGAL_TAGS, LegalLayout, LegalSection } from '@/components/LegalLayout'
import { LONG_DATE } from '@/i18n/format'
import { LEGAL_UPDATED_ON } from '@/lib/legal-dates'
import { COOKIES, LOCAL_STORAGE, SESSION_STORAGE, type StorageRow } from './storage-keys'

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations('legal.cookie')
  return { title: t('title'), description: t('intro') }
}

export default async function CookiePage() {
  const t = await getTranslations('legal.cookie')
  const format = await getFormatter()
  const rich = (key: string) => t.rich(key, LEGAL_TAGS)

  const table = (rows: StorageRow[]) => (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-small">
        <thead>
          <tr className="border-b border-rule text-left text-ink-2">
            <th className="py-2 pr-4 font-semibold">{t('colKey')}</th>
            <th className="py-2 pr-4 font-semibold">{t('colPurpose')}</th>
            <th className="py-2 font-semibold">{t('colDuration')}</th>
          </tr>
        </thead>
        <tbody className="align-top">
          {rows.map((row) => (
            <tr key={row.key} className="border-b border-rule">
              <td className="py-2 pr-4 font-mono text-ink">{row.key}</td>
              <td className="py-2 pr-4">{t(`rows.${row.id}.purpose`)}</td>
              <td className="py-2">{t(`rows.${row.id}.duration`)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )

  return (
    <LegalLayout title={t('title')} intro={t('intro')} lastUpdated={format.dateTime(LEGAL_UPDATED_ON, LONG_DATE)}>
      <LegalSection title={t('scope.title')}>
        <p>{rich('scope.p')}</p>
      </LegalSection>

      <LegalSection title={t('cookies.title')}>
        <p>{rich('cookies.p1')}</p>
        <p>{t('cookies.p2')}</p>
        {table(COOKIES)}
      </LegalSection>

      <LegalSection title={t('storage.title')}>
        <p>{t('storage.p1')}</p>
        <p>{rich('storage.p2')}</p>
        {table(LOCAL_STORAGE)}
        <p>{rich('storage.p3')}</p>
        {table(SESSION_STORAGE)}
      </LegalSection>

      <LegalSection title={t('thirdParty.title')}>
        <p>{rich('thirdParty.p1')}</p>
        <p>{t('thirdParty.p2')}</p>
      </LegalSection>

      <LegalSection title={t('basis.title')}>
        <p>{t('basis.p')}</p>
      </LegalSection>

      <LegalSection title={t('manage.title')}>
        <p>{t('manage.p')}</p>
      </LegalSection>

      <LegalSection title={t('contacts.title')}>
        <p>{rich('contacts.p')}</p>
      </LegalSection>
    </LegalLayout>
  )
}
