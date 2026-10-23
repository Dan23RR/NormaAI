import type { Metadata, Viewport } from 'next'
import { Literata, Public_Sans, Geist_Mono } from 'next/font/google'
import { Analytics } from '@vercel/analytics/react'
import { NextIntlClientProvider } from 'next-intl'
import { getLocale, getMessages, getTranslations } from 'next-intl/server'
import './globals.css'
import { AuthProvider } from '@/hooks/useAuth'
import { ToastProvider } from '@/components/ui/Toast'
import { CookieBanner } from '@/components/CookieBanner'
import { LocaleSync } from '@/i18n/LocaleSync'
import { languageOf } from '@/i18n/config'

// Self-hosted by next/font: no external request, no layout shift, CSP
// font-src 'self' stays intact. Literata carries the text of the law and
// the headings (optical sizes on), Public Sans carries the interface.
const serif = Literata({
  subsets: ['latin', 'latin-ext'],
  axes: ['opsz'],
  style: ['normal', 'italic'],
  variable: '--font-serif',
  display: 'swap',
})

const sans = Public_Sans({
  subsets: ['latin', 'latin-ext'],
  variable: '--font-sans',
  display: 'swap',
})

const mono = Geist_Mono({
  subsets: ['latin'],
  variable: '--font-mono',
  display: 'swap',
})

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || 'https://normaai.org'

const KEYWORDS = [
  'CSRD',
  'CSDDD',
  'AI Act',
  'DORA',
  'NIS2',
  'Tassonomia UE',
  'EU Taxonomy',
  'GDPR',
  'compliance UE',
  'EU compliance',
  'EUR-Lex',
  'Normattiva',
  'compliance officer',
  'consulenza ESG',
]

/** Title, description and Open Graph in the language of the request. */
export async function generateMetadata(): Promise<Metadata> {
  const locale = await getLocale()
  const t = await getTranslations('site.meta')
  return {
    metadataBase: new URL(SITE_URL),
    title: {
      default: t('title'),
      template: '%s | NormaAI',
    },
    description: t('description'),
    keywords: KEYWORDS,
    openGraph: {
      title: t('title'),
      description: t('ogDescription'),
      url: SITE_URL,
      images: [{ url: '/og-image.png', width: 1200, height: 630 }],
      type: 'website',
      locale: languageOf(locale) === 'en' ? 'en_GB' : 'it_IT',
    },
    twitter: { card: 'summary_large_image' },
    robots: { index: true, follow: true },
  }
}

export const viewport: Viewport = {
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#FFFFFF' },
    { media: '(prefers-color-scheme: dark)', color: '#0B1220' },
  ],
}

// Applies the saved theme before first paint. Light is the default; dark
// only when the person chose it (or chose "system" on a dark OS).
const themeScript = `try{var t=localStorage.getItem('normaai.theme');if(t==='dark'||(t==='system'&&window.matchMedia('(prefers-color-scheme: dark)').matches)){document.documentElement.classList.add('dark')}}catch(e){}`

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const locale = await getLocale()
  const messages = await getMessages()
  const t = await getTranslations('site.meta')

  const jsonLd = {
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'Organization',
        '@id': `${SITE_URL}/#org`,
        name: 'NormaAI',
        url: SITE_URL,
        logo: `${SITE_URL}/og-image.png`,
        email: 'info@normaai.org',
        description: t('orgDescription'),
      },
      {
        '@type': 'SoftwareApplication',
        name: 'NormaAI',
        applicationCategory: 'BusinessApplication',
        operatingSystem: 'Web',
        url: SITE_URL,
        description: t('appDescription'),
        offers: {
          '@type': 'Offer',
          price: '0',
          priceCurrency: 'EUR',
          description: t('offer'),
        },
        provider: { '@id': `${SITE_URL}/#org` },
      },
    ],
  }

  return (
    <html lang={locale} className={`${serif.variable} ${sans.variable} ${mono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
        <NextIntlClientProvider locale={locale} messages={messages} timeZone="Europe/Rome">
          <AuthProvider>
            <ToastProvider>
              {children}
              <CookieBanner />
            </ToastProvider>
          </AuthProvider>
          <LocaleSync />
        </NextIntlClientProvider>
        {/* Cookieless, GDPR-friendly (no personal data, no consent needed).
            Activates once Analytics is enabled on the Vercel project. */}
        <Analytics />
      </body>
    </html>
  )
}
