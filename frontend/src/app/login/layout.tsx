import type { Metadata } from 'next'
import type { ReactNode } from 'react'
import { getTranslations } from 'next-intl/server'

// The page itself is a client component, so its title lives here. Sign-in is
// not a page to index (robots.ts also keeps crawlers away from it).
export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations('login')
  return {
    title: t('metaTitle'),
    description: t('metaDescription'),
    robots: { index: false, follow: true },
  }
}

export default function LoginLayout({ children }: { children: ReactNode }) {
  return children
}
