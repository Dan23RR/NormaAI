const createNextIntlPlugin = require('next-intl/plugin')

// Italian and English without a locale in the URL: the language is read from
// the `normaai.locale` cookie in src/i18n/request.ts.
const withNextIntl = createNextIntlPlugin('./src/i18n/request.ts')

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  poweredByHeader: false, // don't advertise the framework
  async redirects() {
    return [
      // The application moved from /dashboard to /app (v2); old links keep working.
      { source: '/dashboard', destination: '/app', permanent: true },
      { source: '/dashboard/overview', destination: '/app', permanent: true },
      { source: '/dashboard/qa', destination: '/app/chiedi', permanent: true },
      { source: '/dashboard/gap-analysis', destination: '/app/clienti', permanent: true },
      { source: '/dashboard/monitor', destination: '/app/monitoraggio', permanent: true },
      { source: '/dashboard/alerts', destination: '/app/monitoraggio', permanent: true },
      { source: '/dashboard/clients', destination: '/app/clienti', permanent: true },
      { source: '/dashboard/clients/:id', destination: '/app/clienti/:id', permanent: true },
      { source: '/dashboard/reports', destination: '/app/report', permanent: true },
      { source: '/dashboard/admin', destination: '/app/admin', permanent: true },
      { source: '/dashboard/:path*', destination: '/app', permanent: false },
    ]
  },
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          // The Content-Security-Policy is set in src/middleware.ts (single source).
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff',
          },
          {
            key: 'X-Frame-Options',
            value: 'DENY',
          },
          {
            key: 'Referrer-Policy',
            value: 'strict-origin-when-cross-origin',
          },
          {
            key: 'Permissions-Policy',
            value: 'camera=(), microphone=(), geolocation=(), payment=()',
          },
          {
            // Vercel serves HTTPS; safe to assert HSTS.
            key: 'Strict-Transport-Security',
            value: 'max-age=63072000; includeSubDomains; preload',
          },
        ],
      },
    ]
  },
}

module.exports = withNextIntl(nextConfig)
