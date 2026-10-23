import type { Metadata, Viewport } from 'next'
import { Literata, Public_Sans, Geist_Mono } from 'next/font/google'
import { Analytics } from '@vercel/analytics/react'
import './globals.css'
import { AuthProvider } from '@/hooks/useAuth'
import { LocaleProvider } from '@/hooks/useLocale'
import { ToastProvider } from '@/components/ui/Toast'
import { CookieBanner } from '@/components/CookieBanner'

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

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: 'NormaAI: risposte sul diritto UE con la fonte esatta',
    template: '%s | NormaAI',
  },
  description:
    "Domande su CSRD, CSDDD, AI Act, NIS2, DORA, GDPR e Tassonomia UE con l'articolo citato e il passaggio di legge verificabile su EUR-Lex e Normattiva.",
  keywords: [
    'CSRD',
    'CSDDD',
    'AI Act',
    'DORA',
    'NIS2',
    'Tassonomia UE',
    'GDPR',
    'compliance UE',
    'EUR-Lex',
    'Normattiva',
    'compliance officer',
    'consulenza ESG',
  ],
  openGraph: {
    title: 'NormaAI: risposte sul diritto UE con la fonte esatta',
    description:
      "Ogni risposta cita l'atto, l'articolo e il passaggio di legge, con il link al testo ufficiale. Se il testo non basta, il sistema lo dice.",
    url: SITE_URL,
    images: [{ url: '/og-image.png', width: 1200, height: 630 }],
    type: 'website',
    locale: 'it_IT',
  },
  twitter: { card: 'summary_large_image' },
  robots: { index: true, follow: true },
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
      description:
        'Risposte sul diritto UE (CSRD, CSDDD, AI Act, DORA, NIS2, Tassonomia, GDPR) con la fonte esatta su EUR-Lex e Normattiva.',
    },
    {
      '@type': 'SoftwareApplication',
      name: 'NormaAI',
      applicationCategory: 'BusinessApplication',
      operatingSystem: 'Web',
      url: SITE_URL,
      description:
        "Domande e risposte sul diritto UE con citazione dell'atto, dell'articolo e del passaggio di legge; verifica di ambito per azienda; monitoraggio delle scadenze.",
      offers: {
        '@type': 'Offer',
        price: '0',
        priceCurrency: 'EUR',
        description: 'Accesso su invito. Codex Post-Omnibus 2025-2029 gratuito.',
      },
      provider: { '@id': `${SITE_URL}/#org` },
    },
  ],
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="it" className={`${serif.variable} ${sans.variable} ${mono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
        <AuthProvider>
          <LocaleProvider>
            <ToastProvider>
              {children}
              <CookieBanner />
            </ToastProvider>
          </LocaleProvider>
        </AuthProvider>
        {/* Cookieless, GDPR-friendly (no personal data, no consent needed).
            Activates once Analytics is enabled on the Vercel project. */}
        <Analytics />
      </body>
    </html>
  )
}
