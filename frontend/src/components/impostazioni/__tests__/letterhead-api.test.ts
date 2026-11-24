import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ApiError } from '@/lib/api-error'

const mocks = vi.hoisted(() => ({ fetchBlob: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: { fetchBlob: mocks.fetchBlob } }))

import { asLetterhead, fetchLogo, linesOf, logoProblem, textProblems } from '../letterhead-api'

const texts = (fields: Partial<Record<'name' | 'address' | 'contact' | 'footer_note', string>>) => ({
  name: 'Studio Alfa',
  address: '',
  contact: '',
  footer_note: '',
  ...fields,
})

describe('the letterhead API', () => {
  beforeEach(() => vi.clearAllMocks())

  it('settles every field the server sends, or leaves out', () => {
    expect(asLetterhead(null)).toEqual({
      configured: false,
      name: '',
      address: null,
      contact: null,
      footer_note: null,
      logo: null,
      updated_at: null,
    })
    expect(
      asLetterhead({
        configured: true,
        name: 'Studio Alfa',
        address: 'Via Roma 1',
        contact: '  ',
        logo: { content_type: 'image/png', size: 'tanto' },
        updated_at: '2026-11-24T10:00:00+00:00',
      }),
    ).toEqual({
      configured: true,
      name: 'Studio Alfa',
      address: 'Via Roma 1',
      contact: null,
      footer_note: null,
      logo: { content_type: 'image/png', size: 0 },
      updated_at: '2026-11-24T10:00:00+00:00',
    })
    expect(asLetterhead({ logo: { size: 3 } }).logo).toBeNull()
  })

  it('reads the lines of a text as the server keeps them', () => {
    expect(linesOf('  Via Roma   1 \r\n\n\n20121 Milano\u2028Italia ')).toEqual(['Via Roma 1', '20121 Milano', 'Italia'])
    expect(linesOf('   ')).toEqual([])
  })

  it('finds what the server would refuse in the texts', () => {
    expect(textProblems(texts({}))).toEqual({})
    expect(textProblems(texts({ name: '  ' }))).toEqual({ name: 'nameMissing' })
    expect(textProblems(texts({ name: 'x'.repeat(201) }))).toEqual({ name: 'nameLong' })
    expect(textProblems(texts({ address: 'a\nb\nc\nd' }))).toEqual({ address: 'addressLines' })
    expect(textProblems(texts({ address: 'a'.repeat(301) }))).toEqual({ address: 'addressLong' })
    expect(textProblems(texts({ address: 'a\n\n\nb\n\nc' }))).toEqual({}) // empty lines do not count
    expect(textProblems(texts({ contact: 'c'.repeat(201), footer_note: 'n'.repeat(301) }))).toEqual({
      contact: 'contactLong',
      footer_note: 'footerLong',
    })
  })

  it('finds what the server would refuse in a logo file', () => {
    expect(logoProblem(new File(['x'], 'logo.png', { type: 'image/png' }))).toBeNull()
    expect(logoProblem(new File(['x'], 'logo.jpg', { type: 'image/jpeg' }))).toBeNull()
    expect(logoProblem(new File(['x'], 'logo.svg', { type: 'image/svg+xml' }))).toBe('logoType')
    expect(logoProblem(new File([], 'logo.png', { type: 'image/png' }))).toBe('logoEmpty')
    expect(logoProblem(new File([new Uint8Array(2 * 1024 * 1024 + 1)], 'logo.png', { type: 'image/png' }))).toBe('logoHeavy')
  })

  it('reads no logo as null and lets any other failure through', async () => {
    mocks.fetchBlob.mockRejectedValueOnce(new ApiError('requestFailed', { values: { status: '404' } }))
    expect(await fetchLogo()).toBeNull()
    mocks.fetchBlob.mockRejectedValueOnce(new ApiError('requestFailed', { values: { status: '500' } }))
    await expect(fetchLogo()).rejects.toBeInstanceOf(ApiError)
    mocks.fetchBlob.mockResolvedValueOnce(new Response(new Blob(['png'], { type: 'image/png' })))
    expect(await (await fetchLogo())?.text()).toBe('png')
  })
})
