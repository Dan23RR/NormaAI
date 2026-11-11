import { describe, expect, it } from 'vitest'
import sitemap from '../sitemap'
import { LEGAL_UPDATED_ON } from '@/lib/legal-dates'

describe('sitemap', () => {
  const entries = sitemap()
  const byPath = new Map(entries.map((e) => [new URL(e.url).pathname, e]))

  it('lists every public page once, the two static checkers included', () => {
    expect([...byPath.keys()].sort()).toEqual(
      ['/', '/cookie', '/metodo', '/privacy', '/scope-aiact.html', '/scope-csrd.html', '/security', '/terms'].sort(),
    )
    expect(entries).toHaveLength(byPath.size)
  })

  it('lists no page that robots.txt keeps crawlers away from', () => {
    for (const path of byPath.keys()) {
      expect(path.startsWith('/app'), path).toBe(false)
      expect(path.startsWith('/login'), path).toBe(false)
      expect(path.startsWith('/api'), path).toBe(false)
    }
  })

  it('dates each page with a real day, the legal pages with the date printed on them', () => {
    const now = Date.now()
    for (const entry of entries) {
      const modified = new Date(entry.lastModified as Date).getTime()
      expect(modified, entry.url).toBeLessThanOrEqual(now)
      expect(modified, entry.url).toBeGreaterThanOrEqual(Date.UTC(2026, 10, 11))
    }
    for (const path of ['/security', '/privacy', '/terms', '/cookie']) {
      expect(byPath.get(path)?.lastModified).toEqual(LEGAL_UPDATED_ON)
    }
  })
})
