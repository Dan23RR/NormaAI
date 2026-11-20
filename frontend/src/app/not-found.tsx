import type { Metadata } from 'next'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { getTranslations } from 'next-intl/server'
import { SiteHeader } from '@/components/site/SiteHeader'
import { SiteFooter } from '@/components/site/SiteFooter'
import { ButtonLink } from '@/components/ui/Button'

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations('site.notFound')
  return { title: t('title'), robots: { index: false, follow: true } }
}

/** Any address that matches no page: says so, and offers the pages that exist. */
export default function NotFound() {
  const t = useTranslations('site.notFound')
  const tf = useTranslations('site.footer')
  return (
    <div className="flex min-h-screen flex-col bg-surface text-ink">
      <SiteHeader compact />
      <main className="mx-auto w-full max-w-3xl flex-1 px-6 py-16 md:py-24">
        <h1 className="text-h1 md:text-display">{t('title')}</h1>
        <p className="mt-4 max-w-prose text-read text-ink-2">{t('body')}</p>
        <div className="mt-8">
          <ButtonLink href="/">{t('home')}</ButtonLink>
        </div>
        <h2 className="mt-12 font-sans text-small font-semibold text-ink">{t('elsewhere')}</h2>
        <ul className="mt-3 space-y-2 text-body">
          <li>
            <a href="/scope-csrd.html" className="text-union underline hover:no-underline">
              {tf('scopeCsrd')}
            </a>
          </li>
          <li>
            <a href="/scope-aiact.html" className="text-union underline hover:no-underline">
              {tf('scopeAiAct')}
            </a>
          </li>
          <li>
            <Link href="/metodo" className="text-union underline hover:no-underline">
              {tf('method')}
            </Link>
          </li>
        </ul>
      </main>
      <SiteFooter />
    </div>
  )
}
