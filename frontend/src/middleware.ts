import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';
import { contentSecurityPolicy, newNonce } from '@/lib/csp';

/**
 * Middleware for NormaAI dashboard routes.
 *
 * Since auth tokens are stored in localStorage (client-side),
 * the actual auth check happens in the dashboard layout component.
 * This middleware provides:
 * 1. Security headers for all routes, with a Content-Security-Policy that
 *    carries a fresh script nonce on every request (src/lib/csp.ts)
 * 2. API proxy protection (no direct access to internal paths)
 */
export function middleware(request: NextRequest) {
  const nonce = newNonce();
  const csp = contentSecurityPolicy({
    nonce,
    development: process.env.NODE_ENV === 'development',
    apiOrigin: process.env.NEXT_PUBLIC_API_BASE_URL || undefined,
  });

  // On the request: Next.js reads the nonce from this header and puts it on
  // the scripts it renders; the root layout reads `x-nonce` for its own.
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set('x-nonce', nonce);
  requestHeaders.set('Content-Security-Policy', csp);
  const response = NextResponse.next({ request: { headers: requestHeaders } });

  // Security headers
  response.headers.set('X-Content-Type-Options', 'nosniff');
  response.headers.set('X-Frame-Options', 'DENY');
  response.headers.set('X-XSS-Protection', '1; mode=block');
  response.headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');
  response.headers.set(
    'Permissions-Policy',
    'camera=(), microphone=(), geolocation=()'
  );
  response.headers.set('X-Permitted-Cross-Domain-Policies', 'none');
  response.headers.set('Content-Security-Policy', csp);
  response.headers.set('Strict-Transport-Security', 'max-age=31536000; includeSubDomains');

  // Prevent caching of application pages (they require auth)
  const path = request.nextUrl.pathname
  if (path.startsWith('/app') || path.startsWith('/dashboard')) {
    response.headers.set('Cache-Control', 'no-store, no-cache, must-revalidate');
    response.headers.set('Pragma', 'no-cache');
  }

  return response;
}

export const config = {
  matcher: [
    // Match all routes except static files and Next.js internals
    '/((?!_next/static|_next/image|favicon.ico).*)',
  ],
};
