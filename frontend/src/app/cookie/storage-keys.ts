/**
 * Every cookie and browser-storage key the frontend sets, as the cookie
 * policy lists them. The words (purpose, duration) live in the
 * `legal.cookie.rows` messages under each `id`.
 *
 * This list is checked against the source by __tests__/storage-keys.test.ts:
 * a key used in src/ and missing here, or listed here and used nowhere,
 * fails the build. A trailing `*` stands for a per-item suffix (one key per
 * client, for example).
 */
import { LOCALE_COOKIE } from '@/i18n/config'

export type StorageRow = { id: string; key: string }

export const COOKIES: StorageRow[] = [{ id: 'localeCookie', key: LOCALE_COOKIE }]

export const LOCAL_STORAGE: StorageRow[] = [
  { id: 'accessToken', key: 'normaai_access_token' },
  { id: 'refreshToken', key: 'normaai_refresh_token' },
  { id: 'demoMode', key: 'normaai_demo_mode' },
  { id: 'locale', key: 'normaai_locale' },
  { id: 'theme', key: 'normaai.theme' },
  { id: 'cookieBanner', key: 'normaai.cookie-banner.dismissed' },
  { id: 'sidebar', key: 'normaai_sidebar_collapsed' },
  { id: 'qaLanguage', key: 'normaai_qa_language' },
]

export const SESSION_STORAGE: StorageRow[] = [
  { id: 'companyProfile', key: 'normaai_company_profile' },
  { id: 'qaMessages', key: 'normaai_qa_messages' },
  { id: 'clientGap', key: 'normaai_client_gap_*' },
  { id: 'demoReports', key: 'normaai_demo_reports' },
  { id: 'demoClients', key: 'normaai_demo_clients' },
  { id: 'demoClientsDeleted', key: 'normaai_demo_clients_deleted' },
  { id: 'demoInvites', key: 'normaai_demo_invites' },
]
