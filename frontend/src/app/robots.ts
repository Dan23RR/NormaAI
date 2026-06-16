import type { MetadataRoute } from 'next'

// Until normaai.org points to Vercel, the canonical host is the staging URL.
// Set NEXT_PUBLIC_SITE_URL on Vercel when the custom domain goes live.
const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || 'https://normaai-psi.vercel.app'

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: '*',
        allow: '/',
        disallow: ['/dashboard/', '/login', '/api/'],
      },
    ],
    sitemap: `${SITE_URL}/sitemap.xml`,
  }
}
