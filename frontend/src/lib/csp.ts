/**
 * The Content-Security-Policy of the site, built for each request by
 * src/middleware.ts.
 *
 * Scripts: only from the site itself, plus inline scripts that carry the
 * nonce of the request or whose hash is listed below. No 'unsafe-inline' and,
 * outside development, no 'unsafe-eval'.
 * - Next.js finds the nonce in the Content-Security-Policy header of the
 *   request (the middleware sets it there too) and puts it on every script
 *   it renders; the root layout reads it from `x-nonce` for the theme script.
 *   A nonce changes at every request, so a page that carries one cannot be
 *   prerendered: every page of the site is already rendered per request,
 *   because the language comes from a cookie (`next build` lists them all as
 *   dynamic), so the nonce costs no static page.
 * - The static pages of public/ (the two checkers) are files served as they
 *   are, with no nonce: their inline scripts are allowed by hash.
 *
 * Styles keep 'unsafe-inline': React and next/font write style attributes and
 * inline styles, and an injected style cannot run code.
 */

/**
 * SHA-256 of the inline scripts of the static pages in public/, as a browser
 * computes it: over the text between <script> and </script>, with line breaks
 * read as LF (the HTML parser normalises CRLF). The theme script is the same
 * in both pages. src/lib/__tests__/csp.test.ts recomputes them from the files
 * and prints the new value when a script changes.
 */
export const STATIC_PAGE_SCRIPT_HASHES = [
  // scope-aiact.html and scope-csrd.html: the theme script in <head>
  "'sha256-N3jFt6F0dDjB47XUo8XF80lV7u7Y/XQ9ifJ3z5CtNwg='",
  // scope-aiact.html: the checker
  "'sha256-5CWTBo3qY9VCHDZ/Jy0wPgWRAxu3LwsYW7ndi6RTV3Q='",
  // scope-csrd.html: the checker
  "'sha256-AfQ7iphKwFlwz0H9t8tsTzRygtcSh4jyDBbFwe24xx4='",
] as const

/** A fresh nonce: 128 random bits in base64, the alphabet Next.js reads. */
export function newNonce(): string {
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes)
  let binary = ''
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return btoa(binary)
}

export function contentSecurityPolicy({
  nonce,
  development,
  apiOrigin,
}: {
  nonce: string
  /** `next dev`: React needs eval for its debugging, and Vercel Analytics loads its debug script from its own host. */
  development: boolean
  /** NEXT_PUBLIC_API_BASE_URL, which the browser calls directly. */
  apiOrigin?: string
}): string {
  const scripts = ["'self'", `'nonce-${nonce}'`, ...STATIC_PAGE_SCRIPT_HASHES]
  if (development) scripts.push("'unsafe-eval'", 'https://va.vercel-scripts.com')
  return [
    "default-src 'self'",
    `script-src ${scripts.join(' ')}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    `connect-src 'self'${apiOrigin ? ` ${apiOrigin}` : ''}`,
    "object-src 'none'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
  ].join('; ')
}
