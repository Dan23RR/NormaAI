import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

/**
 * The two static checkers (public/scope-*.html) are served as they are: no
 * build step, no shared stylesheet. These checks keep what must not drift:
 * the identity (frontend/DESIGN.md), the self-contained page the Content
 * Security Policy allows, the lead contract of /api/leads, and the copy that
 * went stale once (a passed deadline sold as upcoming).
 */

const PUBLIC = join(__dirname, '..', '..', '..', 'public')
const read = (name: string) => readFileSync(join(PUBLIC, name), 'utf8')

const PAGES = [
  { name: 'scope-aiact.html', url: 'https://normaai.org/scope-aiact.html' },
  { name: 'scope-csrd.html', url: 'https://normaai.org/scope-csrd.html' },
]

describe.each(PAGES)('static checker $name', ({ name, url }) => {
  const html = read(name)

  it('declares canonical, description and share image', () => {
    expect(html).toContain(`<link rel="canonical" href="${url}">`)
    expect(html).toMatch(/<meta name="description" content="[^"]{80,}">/)
    expect(html).toContain('<meta property="og:image" content="https://normaai.org/og-image.png">')
    expect(html).toContain(`<meta property="og:url" content="${url}">`)
  })

  it('is on the v2 identity, with nothing of the retired one', () => {
    for (const token of ['#0C1B33', '#0A3A9C', '#FFEA7A', '#F5C400']) expect(html).toContain(token)
    expect(html).toContain('Literata,Georgia,"Times New Roman",serif')
    expect(html).toContain('"Public Sans",system-ui,-apple-system,"Segoe UI",sans-serif')
    // warm paper, clay accent, gradients, uppercase eyebrow, mono labels
    for (const retired of ['#FAF9F5', '#D97757', '#C2613F', 'gradient', 'text-transform', 'eyebrow', 'Geist Mono', 'Source Serif']) {
      expect(html, retired).not.toContain(retired)
    }
  })

  it('loads nothing from outside the page', () => {
    expect(html).not.toMatch(/<link[^>]+rel="stylesheet"/)
    expect(html).not.toMatch(/<script[^>]+src=/)
    expect(html).not.toMatch(/@import|url\(/)
    expect(html).not.toMatch(/<img|<iframe/)
  })

  it('keeps every size at 12 px or more', () => {
    const sizes = [...html.matchAll(/font-size:\s*([\d.]+)px/g)].map((m) => Number(m[1]))
    expect(sizes.length).toBeGreaterThan(10)
    expect(Math.min(...sizes)).toBeGreaterThanOrEqual(12)
  })

  it('keeps the lead form contract of /api/leads', () => {
    expect(html).toContain("fetch('/api/leads'")
    expect(html).toContain('id="contact_time" name="contact_time"')
    expect(html).toContain('contact_time:hp')
    expect(html).toMatch(/id="org"/)
    expect(html).toMatch(/type="email" id="email"/)
  })

  it('offers a 30 minute call and uses no dash, ellipsis or curly quote characters', () => {
    expect(html).toContain('30 minuti')
    expect(html).not.toContain('20 minuti')
    expect(html).not.toMatch(/[–—…“”‘]/)
  })
})

describe('AI Act checker', () => {
  const html = read('scope-aiact.html')

  it('sends the same source values as before', () => {
    expect(html).toContain("var src = 'aiact_checker:' + band + ((keys && keys.length) ? ':' + keys.join('+') : '');")
    expect(html).toContain("role:'aiact_checker', source:src, lead_ref:'scope-aiact'")
  })

  it('treats article 50 as law in force and names the next date', () => {
    expect(html).toContain('2 dicembre 2026')
    expect(html).toContain('regolamento (UE) 2026/1744')
    expect(html).toContain('02024R1689-20260727')
    expect(html).toMatch(/Aggiornato all\\?.11 novembre 2026/)
    for (const stale of ['il 2 agosto ti riguarda', 'scadenza 2 agosto', 'entro agosto', '12 luglio 2026', 'via libera']) {
      expect(html, stale).not.toContain(stale)
    }
  })
})

describe('CSRD checker', () => {
  const html = read('scope-csrd.html')

  it('sends the same source values as before', () => {
    expect(html).toContain("role:'scope_checker', source:'scope_checker:'+band, lead_ref:'scope-csrd'")
  })

  it('keeps the thresholds and the classification rule', () => {
    expect(html).toContain('var EMP_T = 1000;')
    expect(html).toContain('var REV_T = 450;')
    expect(html).toContain('var CSDDD_EMP = 5000, CSDDD_REV = 1500;')
    expect(html).toContain("if (empOver && revOver) return 'in';")
    expect(html).toContain("if (empOver || revOver) return 'filo';")
    expect(html).toContain('var empMargin = emp >= 850 && emp <= 1200;')
    expect(html).toContain('var revMargin = rev >= 380 && rev <= 550;')
  })

  it('carries no figure without a primary source', () => {
    for (const unsourced of ['80%', '61%', 'GAR']) expect(html, unsourced).not.toContain(unsourced)
  })
})
