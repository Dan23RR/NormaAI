// @vitest-environment node
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createHash } from 'node:crypto'
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { NextRequest } from 'next/server'
import { STATIC_PAGE_SCRIPT_HASHES, contentSecurityPolicy, newNonce } from '../csp'
import { middleware } from '../../middleware'

const PUBLIC = join(__dirname, '..', '..', '..', 'public')

/** The directives of a policy, by name. */
function directives(policy: string): Map<string, string[]> {
  return new Map(
    policy
      .split(';')
      .map((part) => part.trim().split(/\s+/))
      .map(([name, ...sources]) => [name, sources]),
  )
}

/** The hash a browser computes for each inline script of the static pages. */
function inlineScriptHashes(): Map<string, string[]> {
  const byPage = new Map<string, string[]>()
  for (const name of readdirSync(PUBLIC).filter((file) => file.endsWith('.html'))) {
    // The HTML parser reads CRLF as LF, and git stores these files with LF.
    const html = readFileSync(join(PUBLIC, name), 'utf8').replace(/\r\n?/g, '\n')
    const hashes = [...html.matchAll(/<script(\s[^>]*)?>([\s\S]*?)<\/script>/g)]
      .filter(([, attributes = '']) => !/\ssrc=/.test(attributes))
      .map(([, , body]) => `'sha256-${createHash('sha256').update(body, 'utf8').digest('base64')}'`)
    byPage.set(name, hashes)
  }
  return byPage
}

describe('contentSecurityPolicy', () => {
  const production = directives(contentSecurityPolicy({ nonce: 'abc123', development: false }))

  it('allows scripts from the site, with the nonce or a listed hash, and nothing unsafe in production', () => {
    const scripts = production.get('script-src') ?? []
    expect(scripts.slice(0, 2)).toEqual(["'self'", "'nonce-abc123'"])
    expect(scripts.slice(2)).toEqual([...STATIC_PAGE_SCRIPT_HASHES])
    expect(scripts).not.toContain("'unsafe-inline'")
    expect(scripts).not.toContain("'unsafe-eval'")
  })

  it('keeps inline styles, and closes the rest', () => {
    expect(production.get('style-src')).toEqual(["'self'", "'unsafe-inline'"])
    expect(production.get('default-src')).toEqual(["'self'"])
    expect(production.get('object-src')).toEqual(["'none'"])
    expect(production.get('frame-ancestors')).toEqual(["'none'"])
    expect(production.get('base-uri')).toEqual(["'self'"])
    expect(production.get('form-action')).toEqual(["'self'"])
    expect(production.get('connect-src')).toEqual(["'self'"])
  })

  it('adds eval and the analytics debug host only in development', () => {
    const development = directives(contentSecurityPolicy({ nonce: 'abc123', development: true }))
    expect(development.get('script-src')).toEqual(
      expect.arrayContaining(["'unsafe-eval'", 'https://va.vercel-scripts.com']),
    )
    expect(production.get('script-src')).not.toContain('https://va.vercel-scripts.com')
  })

  it('lets the browser call the API origin when one is configured', () => {
    const policy = directives(contentSecurityPolicy({ nonce: 'n', development: false, apiOrigin: 'https://api.example.test' }))
    expect(policy.get('connect-src')).toEqual(["'self'", 'https://api.example.test'])
  })
})

describe('the hashes of the static pages', () => {
  it('cover every inline script of public/, and nothing else', () => {
    const pages = inlineScriptHashes()
    const found = new Set([...pages.values()].flat())
    // When a script of a static page changes, the browser refuses it until its
    // new hash is in STATIC_PAGE_SCRIPT_HASHES (src/lib/csp.ts): the message
    // lists the hashes of the files as they are now.
    expect([...STATIC_PAGE_SCRIPT_HASHES].sort(), JSON.stringify(Object.fromEntries(pages), null, 2)).toEqual([...found].sort())
    expect(pages.get('scope-aiact.html')).toHaveLength(2)
    expect(pages.get('scope-csrd.html')).toHaveLength(2)
  })
})

describe('newNonce', () => {
  it('is 128 random bits in base64, new every time', () => {
    const nonces = new Set(Array.from({ length: 50 }, () => newNonce()))
    expect(nonces.size).toBe(50)
    for (const nonce of nonces) expect(nonce).toMatch(/^[A-Za-z0-9+/]{22}==$/)
  })
})

describe('middleware', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  const run = (path = '/') => middleware(new NextRequest(`https://normaai.org${path}`))

  it('sends a policy with a fresh nonce, and gives Next.js the same nonce on the request', () => {
    const first = run()
    const policy = first.headers.get('Content-Security-Policy') ?? ''
    const nonce = /'nonce-([^']+)'/.exec(policy)?.[1]
    expect(nonce).toBeTruthy()
    // NextResponse.next({ request: { headers } }) passes the request headers
    // to the page as x-middleware-request-<name>.
    expect(first.headers.get('x-middleware-request-x-nonce')).toBe(nonce)
    expect(first.headers.get('x-middleware-request-content-security-policy')).toBe(policy)
    const second = run().headers.get('Content-Security-Policy')
    expect(second).not.toBe(policy)
  })

  it('has no unsafe script source outside development', () => {
    vi.stubEnv('NODE_ENV', 'production')
    const scripts = directives(run().headers.get('Content-Security-Policy') ?? '').get('script-src') ?? []
    expect(scripts).not.toContain("'unsafe-inline'")
    expect(scripts).not.toContain("'unsafe-eval'")
  })

  it('serves the static checkers the same policy, which allows their scripts by hash', () => {
    const scripts = directives(run('/scope-aiact.html').headers.get('Content-Security-Policy') ?? '').get('script-src') ?? []
    for (const hash of inlineScriptHashes().get('scope-aiact.html') ?? []) expect(scripts).toContain(hash)
  })

  it('keeps the other security headers, and no cache on the application', () => {
    const app = run('/app/controlla')
    expect(app.headers.get('X-Frame-Options')).toBe('DENY')
    expect(app.headers.get('X-Content-Type-Options')).toBe('nosniff')
    expect(app.headers.get('Referrer-Policy')).toBe('strict-origin-when-cross-origin')
    expect(app.headers.get('Strict-Transport-Security')).toContain('max-age=')
    expect(app.headers.get('Cache-Control')).toContain('no-store')
    expect(run('/').headers.get('Cache-Control')).toBeNull()
  })
})
