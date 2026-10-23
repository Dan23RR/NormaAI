import type { Metadata } from 'next'
import { getFormatter, getTranslations } from 'next-intl/server'
import { LEGAL_TAGS, LegalLayout, LegalSection } from '@/components/LegalLayout'
import { LOCALE_COOKIE } from '@/i18n/config'
import { LONG_DATE } from '@/i18n/format'
import { LEGAL_UPDATED_ON } from '@/lib/legal-dates'

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations('legal.cookie')
  return { title: t('title'), description: t('intro') }
}

/** Storage keys verified against frontend/src (grep localStorage / sessionStorage / document.cookie); the words live in `legal.cookie.rows`. */
type StorageRow = { id: string; key: string }

const COOKIES: StorageRow[] = [{ id: 'localeCookie', key: LOCALE_COOKIE }]

const LOCAL_STORAGE: StorageRow[] = [
  { id: 'accessToken', key: 'normaai_access_token' },
  { id: 'refreshToken', key: 'normaai_refresh_token' },
  { id: 'demoMode', key: 'normaai_demo_mode' },
  { id: 'locale', key: 'normaai_locale' },
  { id: 'theme', key: 'normaai.theme' },
  { id: 'cookieBanner', key: 'normaai.cookie-banner.dismissed' },
  { id: 'sidebar', key: 'normaai_sidebar_collapsed' },
  { id: 'alertPrefs', key: 'normaai_alert_prefs' },
  { id: 'qaLanguage', key: 'normaai_qa_language' },
]

const SESSION_STORAGE: StorageRow[] = [
  { id: 'companyProfile', key: 'normaai_company_profile' },
  { id: 'qaMessages', key: 'normaai_qa_messages' },
  { id: 'gapResult', key: 'normaai_gap_result' },
  { id: 'gapScores', key: 'normaai_gap_scores' },
  { id: 'workflowItems', key: 'normaai-workflow-items' },
  { id: 'demoReports', key: 'normaai_demo_reports' },
  { id: 'demoClients', key: 'normaai_demo_clients' },
  { id: 'demoClientsDeleted', key: 'normaai_demo_clients_deleted' },
]

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
