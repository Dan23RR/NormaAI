/** @type {import('next').NextConfig} */

// Security headers applied to every Next-served response (landing + dashboard).
// Rationale: the FastAPI backend already sets these on API responses
// (src/api/middleware.py SecurityHeadersMiddleware), but the Next pages on
// Vercel were shipping NO security headers (there was no next.config). This
// closes that gap. CSP is intentionally omitted here — a strict CSP for Next's
// hydration scripts needs nonce wiring + browser testing; see TODO below.
const securityHeaders = [
  { key: 'X-Frame-Options', value: 'DENY' },
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
  {
    key: 'Permissions-Policy',
    value: 'camera=(), microphone=(), geolocation=(), payment=()',
  },
  // Vercel serves HTTPS; safe to assert HSTS. `preload` is a claim only (no effect
  // until submitted to hstspreload.org).
  {
    key: 'Strict-Transport-Security',
    value: 'max-age=63072000; includeSubDomains; preload',
  },
  // TODO(security): add a Content-Security-Policy once a nonce-based setup is in
  // place (Next injects inline bootstrap scripts). Ship first as
  // Content-Security-Policy-Report-Only and verify in-browser before enforcing.
]

const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false, // don't advertise the framework
  async headers() {
    return [
      {
        source: '/:path*',
        headers: securityHeaders,
      },
    ]
  },
}

export default nextConfig
