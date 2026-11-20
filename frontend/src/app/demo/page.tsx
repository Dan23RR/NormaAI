import type { Metadata } from 'next'
import { getTranslations } from 'next-intl/server'
import { DemoEntry } from '@/components/landing/DemoEntry'

// A doorway into the demo, not a page for search engines.
export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations('landing.demoEntry')
  return { title: t('metaTitle'), robots: { index: false, follow: false } }
}

export default function DemoPage() {
  return <DemoEntry />
}
