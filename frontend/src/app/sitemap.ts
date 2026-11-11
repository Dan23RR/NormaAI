import type { MetadataRoute } from 'next'
import { LEGAL_UPDATED_ON } from '@/lib/legal-dates'

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || 'https://normaai.org'

/**
 * The day the content of a page last changed (UTC). A real date, not "now":
 * a sitemap that claims every page changed today teaches crawlers to ignore
 * it. Update the date of a page when its content changes; the four legal
 * pages share LEGAL_UPDATED_ON, the date printed on them.
 */
const HOME_UPDATED_ON = new Date(Date.UTC(2026, 10, 11))
const METHOD_UPDATED_ON = new Date(Date.UTC(2026, 10, 11))
const CHECKERS_UPDATED_ON = new Date(Date.UTC(2026, 10, 11))

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    { url: `${SITE_URL}/`, lastModified: HOME_UPDATED_ON, changeFrequency: 'weekly', priority: 1 },
    // The two static checkers (frontend/public): public pages like the others.
    { url: `${SITE_URL}/scope-csrd.html`, lastModified: CHECKERS_UPDATED_ON, changeFrequency: 'monthly', priority: 0.8 },
    { url: `${SITE_URL}/scope-aiact.html`, lastModified: CHECKERS_UPDATED_ON, changeFrequency: 'monthly', priority: 0.8 },
    { url: `${SITE_URL}/metodo`, lastModified: METHOD_UPDATED_ON, changeFrequency: 'monthly', priority: 0.8 },
    { url: `${SITE_URL}/security`, lastModified: LEGAL_UPDATED_ON, changeFrequency: 'monthly', priority: 0.4 },
    { url: `${SITE_URL}/privacy`, lastModified: LEGAL_UPDATED_ON, changeFrequency: 'monthly', priority: 0.3 },
    { url: `${SITE_URL}/terms`, lastModified: LEGAL_UPDATED_ON, changeFrequency: 'monthly', priority: 0.3 },
    { url: `${SITE_URL}/cookie`, lastModified: LEGAL_UPDATED_ON, changeFrequency: 'monthly', priority: 0.2 },
  ]
}
