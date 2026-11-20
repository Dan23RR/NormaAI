import type { Metadata } from 'next'
import type { ReactNode } from 'react'
import { getTranslations } from 'next-intl/server'

// The page is a client component, so its title lives here. Like the sign-in
// page, nothing here is for search engines.
export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations('login.passwordReset')
  return {
    title: t('metaTitle'),
    robots: { index: false, follow: false },
  }
}

export default function ResetPasswordLayout({ children }: { children: ReactNode }) {
  return children
}
