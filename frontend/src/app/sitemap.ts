import type { MetadataRoute } from 'next'

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || 'https://normaai-psi.vercel.app'

export default function sitemap(): MetadataRoute.Sitemap {
  const lastModified = new Date('2026-06-11')
  return [
    { url: `${SITE_URL}/`, lastModified, changeFrequency: 'weekly', priority: 1 },
    { url: `${SITE_URL}/metodo`, lastModified, changeFrequency: 'monthly', priority: 0.8 },
    { url: `${SITE_URL}/privacy`, lastModified, changeFrequency: 'monthly', priority: 0.3 },
    { url: `${SITE_URL}/terms`, lastModified, changeFrequency: 'monthly', priority: 0.3 },
    { url: `${SITE_URL}/security`, lastModified, changeFrequency: 'monthly', priority: 0.4 },
    { url: `${SITE_URL}/cookie`, lastModified, changeFrequency: 'monthly', priority: 0.2 },
  ]
}
