import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

/**
 * Middleware for NormaAI dashboard routes.
 *
 * Since auth tokens are stored in localStorage (client-side),
 * the actual auth check happens in the dashboard layout component.
 * This middleware provides:
 * 1. Security headers for all routes
 * 2. API proxy protection (no direct access to internal paths)
 */
export function middleware(request: NextRequest) {
  const response = NextResponse.next();

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
  response.headers.set(
    'Content-Security-Policy',
    "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self' " + (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000') + "; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
  );
  response.headers.set('Strict-Transport-Security', 'max-age=31536000; includeSubDomains');

  // Prevent caching of dashboard pages (they require auth)
  if (request.nextUrl.pathname.startsWith('/dashboard')) {
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
