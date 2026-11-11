import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, it, expect } from 'vitest'
import itMessages from '../../../messages/it.json'
import enMessages from '../../../messages/en.json'

/**
 * The Codex is a print source (public/codex.html) and the PDF built from it
 * by scripts/build_codex_pdf.py. These checks keep the three places that
 * describe it in step: the source, the PDF, the block of the landing page.
 */
const read = (path: string) => readFileSync(resolve(__dirname, '../../../public', path))

const html = read('codex.html').toString('utf-8')
const pdf = read('codex-post-omnibus-2025-2029.pdf').toString('latin1')

/** Pages of a PDF written by Chromium: one "/Type /Page" object each. */
const pdfPages = (pdf.match(/\/Type\s*\/Page(?!s)/g) ?? []).length

const indexEntries = Array.from(
  html.matchAll(/<div class="toc-entry" data-target="([\w-]+)">[\s\S]*?<span class="page-num">p\. (\d+)<\/span>/g),
  (m) => ({ target: m[1], page: Number(m[2]) }),
)

describe('Codex', () => {
  it('is the version the cover says, with a dated verification', () => {
    expect(html).toContain('v1.1, novembre 2026')
    expect(html).toContain("Fonti verificate l'11 novembre 2026")
    expect(html).not.toMatch(/v1\.0|28 aprile 2026/)
  })

  it('has an index that points to chapters that exist, on pages that exist', () => {
    expect(indexEntries.length).toBeGreaterThanOrEqual(8)
    let previous = 2
    for (const { target, page } of indexEntries) {
      expect(html, target).toContain(`<section class="page" id="${target}">`)
      expect(page, target).toBeGreaterThan(previous)
      expect(page, target).toBeLessThanOrEqual(pdfPages)
      previous = page
    }
  })

  it('has as many pages as the landing page says, in both languages', () => {
    expect(pdfPages).toBeGreaterThan(10)
    expect(itMessages.landing.codex.kicker).toContain(`${pdfPages} pagine`)
    expect(enMessages.landing.codex.kicker).toContain(`${pdfPages} pages`)
  })

  it('gives only the public contact', () => {
    expect(html).toContain('info@normaai.org')
    const mailboxes = html.match(/[\w.+-]+@[\w-]+(?:\.[\w-]+)+/g) ?? []
    expect(new Set(mailboxes)).toEqual(new Set(['info@normaai.org']))
    expect(pdf).not.toMatch(/gmail/i)
  })

  it('states the dates of the texts in force and none of the superseded ones', () => {
    // New CSRD scope: financial years starting on or after 1 January 2027.
    expect(html).toContain('inizia dal 1° gennaio 2027')
    expect(html).not.toMatch(/FY ?202\d/)
    // AI Act high-risk: 2 December 2027 (Annex III), 2 August 2028 (Annex I).
    expect(html).toContain('2 dicembre 2027')
    expect(html).toContain('2 agosto 2028')
    expect(html).not.toMatch(/2 ago(sto)? 2027 [^)]*high-risk|High-risk in regulated products/i)
    // CSDDD: transposition by 26 July 2028, application from 26 July 2029.
    expect(html).toContain('26 luglio 2028')
    expect(html).toContain('26 luglio 2029')
    // The electronic format is Delegated Regulation (EU) 2019/815.
    expect(html).not.toContain('2018/815')
    // Statistics and wording the guide could not support.
    expect(html).not.toMatch(/8\/10|80% delle aziende|postponed|\u22125\d%|\u22126\d%/)
  })

  it('follows the cheap rules of the design system', () => {
    expect(html).not.toMatch(/gradient/)
    expect(html).not.toMatch(/text-transform:\s*uppercase/)
    // Nothing under 12 px: 9pt is 12 px.
    const sizes = Array.from(html.matchAll(/font-size:\s*([\d.]+)pt/g), (m) => Number(m[1]))
    expect(Math.min(...sizes)).toBeGreaterThanOrEqual(9)
    // No dashes, ellipsis, curly quotes or middle dots in the text.
    expect(html.match(/[\u2013\u2014\u2026\u2018\u2019\u201c\u201d\u00b7]/)?.[0]).toBeUndefined()
  })
})
