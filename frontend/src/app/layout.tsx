import type { Metadata, Viewport } from 'next'
import { Source_Serif_4, Inter, Geist_Mono } from 'next/font/google'
import { Analytics } from '@vercel/analytics/react'
import './globals.css'
import { AuthProvider } from '@/hooks/useAuth'
import { LocaleProvider } from '@/hooks/useLocale'
import { CookieBanner } from '@/components/CookieBanner'

// Editorial serif for public-page headlines (warm-paper theme).
// Self-hosted by next/font: no external request, no layout shift.
const serif = Source_Serif_4({
  subsets: ['latin'],
  weight: ['400', '600'],
  style: ['normal', 'italic'],
  variable: '--font-serif',
  display: 'swap',
})

// Self-hosted by next/font (variable fonts). Replaces the old globals.css
// @import from Google Fonts, which was both invalid CSS position (after
// @tailwind - Turbopack rejects it) and blocked at runtime by the CSP
// font-src 'self'. Self-hosting serves them from our own origin: CSP-compliant.
const sans = Inter({
  subsets: ['latin'],
  variable: '--font-sans',
  display: 'swap',
})

const mono = Geist_Mono({
  subsets: ['latin'],
  variable: '--font-mono',
  display: 'swap',
})

const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL || 'https://normaai-psi.vercel.app'

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title:
    'NormaAI - Compliance EU con citazioni primary-source verificate | CSRD, AI Act, DORA, NIS2',
  description:
    'Il copilota normativo difendibile in audit per i 7 framework UE. Q&A con citazione primary source EUR-Lex in 30 secondi. CSRD post-Omnibus, AI Act, DORA per intermediari piccoli, NIS2, GDPR.',
  keywords: [
    'CSRD',
    'CSDDD',
    'AI Act',
    'DORA',
    'NIS2',
    'EU Taxonomy',
    'GDPR',
    'compliance EU',
    'EUR-Lex',
    'compliance officer',
    'mid-market',
    'ESG',
    'Omnibus',
    'consulenza ESG Italia',
  ],
  openGraph: {
    title: 'NormaAI - Compliance EU con citazioni primary-source verificate',
    description:
      'Il copilota normativo difendibile in audit per i 7 framework UE. Citazione primary source EUR-Lex in 30 secondi.',
    url: SITE_URL,
    images: [{ url: '/og-image.png', width: 1200, height: 630 }],
    type: 'website',
    locale: 'it_IT',
  },
  twitter: { card: 'summary_large_image' },
  robots: { index: true, follow: true },
}

export const viewport: Viewport = {
  // Warm paper - matches the public landing background.
  themeColor: '#FAF9F5',
}

// Structured data for rich results (Organization + SoftwareApplication).
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
        'Regulatory intelligence AI per i 7 framework EU (CSRD, CSDDD, AI Act, DORA, NIS2, EU Taxonomy, GDPR) con citazioni EUR-Lex verificate.',
    },
    {
      '@type': 'SoftwareApplication',
      name: 'NormaAI',
      applicationCategory: 'BusinessApplication',
      operatingSystem: 'Web',
      url: SITE_URL,
      description:
        'Q&A normativo con citazioni primary-source EUR-Lex, gap analysis multi-framework e monitoraggio delle modifiche regolatorie EU. Pipeline anti-allucinazione Chain-of-Verification.',
      offers: {
        '@type': 'Offer',
        price: '0',
        priceCurrency: 'EUR',
        description: 'Pilot su richiesta - Codex Post-Omnibus 2025-2029 gratuito',
      },
      provider: { '@id': `${SITE_URL}/#org` },
    },
  ],
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="it" className={`dark ${serif.variable} ${sans.variable} ${mono.variable}`}>
      <body className="font-sans">
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
        />
        <AuthProvider>
          <LocaleProvider>
            {children}
            <CookieBanner />
          </LocaleProvider>
        </AuthProvider>
        {/* Cookieless, GDPR-friendly (no personal data, no consent needed).
            Activates once Analytics is enabled on the Vercel project. */}
        <Analytics />
      </body>
    </html>
  )
}
