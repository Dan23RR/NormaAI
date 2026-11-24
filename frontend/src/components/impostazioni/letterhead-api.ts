import { api } from '@/lib/api'
import { ApiError } from '@/lib/api-error'

/**
 * The letterhead of the organisation (src/api/routers/letterhead.py): what
 * heads the PDFs of the checks a consultant hands to a client.
 *
 * - GET    /api/v1/organization/letterhead        -> the letterhead (any member)
 * - PUT    /api/v1/organization/letterhead        {name, address, contact, footer_note} (admins)
 * - DELETE /api/v1/organization/letterhead        -> 204, back to the name of the organisation (admins)
 * - GET    /api/v1/organization/letterhead/logo   -> the image, PNG or JPEG (any member)
 * - PUT    /api/v1/organization/letterhead/logo   multipart `file` -> the letterhead (admins)
 * - DELETE /api/v1/organization/letterhead/logo   -> the letterhead (admins)
 *
 * Without a letterhead the server answers `configured: false` with the name of
 * the organisation, which is what the PDFs carry then. The demo has none of
 * these routes: the section says so and calls nothing.
 */
export const LETTERHEAD_PATH = '/api/v1/organization/letterhead'

/** The limits of the server (src/reports/letterhead.py), checked here first to say so at once. */
export const LIMITS = { name: 200, address: 300, addressLines: 3, contact: 200, footerNote: 300 } as const
export const LOGO_TYPES = ['image/png', 'image/jpeg'] as const
export const LOGO_MAX_BYTES = 2 * 1024 * 1024

export interface LetterheadTexts {
  name: string
  address: string
  contact: string
  footer_note: string
}

export interface Letterhead {
  configured: boolean
  name: string
  address: string | null
  contact: string | null
  footer_note: string | null
  logo: { content_type: string; size: number } | null
  updated_at: string | null
}

type Raw = Record<string, unknown>
const isRecord = (value: unknown): value is Raw => !!value && typeof value === 'object' && !Array.isArray(value)
const textOrNull = (value: unknown): string | null => (typeof value === 'string' && value.trim() ? value : null)

/** What the server sent, with every field settled: a missing one never takes the page down. */
export function asLetterhead(value: unknown): Letterhead {
  const raw = isRecord(value) ? value : {}
  const logo = isRecord(raw.logo) && typeof raw.logo.content_type === 'string' ? raw.logo : null
  return {
    configured: raw.configured === true,
    name: typeof raw.name === 'string' ? raw.name : '',
    address: textOrNull(raw.address),
    contact: textOrNull(raw.contact),
    footer_note: textOrNull(raw.footer_note),
    logo: logo && {
      content_type: String(logo.content_type),
      size: typeof logo.size === 'number' && logo.size > 0 ? logo.size : 0,
    },
    updated_at: textOrNull(raw.updated_at),
  }
}

/** The non-empty lines of a text, as the server keeps them. */
export function linesOf(text: string): string[] {
  return text
    .split(/\r\n|[\r\n\u2028\u2029]/)
    .map((line) => line.replace(/\s+/g, ' ').trim())
    .filter(Boolean)
}

export type TextProblem = 'nameMissing' | 'nameLong' | 'addressLines' | 'addressLong' | 'contactLong' | 'footerLong'

/** What the server would refuse in the texts, field by field, before sending them. */
export function textProblems(texts: LetterheadTexts): Partial<Record<keyof LetterheadTexts, TextProblem>> {
  const problems: Partial<Record<keyof LetterheadTexts, TextProblem>> = {}
  const name = linesOf(texts.name).join(' ')
  if (!name) problems.name = 'nameMissing'
  else if (name.length > LIMITS.name) problems.name = 'nameLong'
  const address = linesOf(texts.address)
  if (address.length > LIMITS.addressLines) problems.address = 'addressLines'
  else if (address.join('\n').length > LIMITS.address) problems.address = 'addressLong'
  if (linesOf(texts.contact).join(' ').length > LIMITS.contact) problems.contact = 'contactLong'
  if (linesOf(texts.footer_note).join(' ').length > LIMITS.footerNote) problems.footer_note = 'footerLong'
  return problems
}

export type LogoProblem = 'logoType' | 'logoHeavy' | 'logoEmpty'

/** What the server would refuse in a logo file at first sight (its type and its weight). */
export function logoProblem(file: File): LogoProblem | null {
  if (!(LOGO_TYPES as readonly string[]).includes(file.type)) return 'logoType'
  if (file.size === 0) return 'logoEmpty'
  if (file.size > LOGO_MAX_BYTES) return 'logoHeavy'
  return null
}

export async function fetchLetterhead(): Promise<Letterhead> {
  return asLetterhead(await api.get<unknown>(LETTERHEAD_PATH))
}

export async function saveLetterhead(texts: LetterheadTexts): Promise<Letterhead> {
  return asLetterhead(await api.put<unknown>(LETTERHEAD_PATH, texts))
}

export async function removeLetterhead(): Promise<void> {
  await api.del<unknown>(LETTERHEAD_PATH)
}

export async function uploadLogo(file: File): Promise<Letterhead> {
  const form = new FormData()
  form.append('file', file)
  return asLetterhead(await api.upload<unknown>(`${LETTERHEAD_PATH}/logo`, form, 'PUT'))
}

export async function removeLogo(): Promise<Letterhead> {
  return asLetterhead(await api.del<unknown>(`${LETTERHEAD_PATH}/logo`))
}

/** The logo as an image to show, or null when the letterhead has none. */
export async function fetchLogo(): Promise<Blob | null> {
  try {
    return await (await api.fetchBlob(`${LETTERHEAD_PATH}/logo`)).blob()
  } catch (err) {
    if (err instanceof ApiError && err.values?.status === '404') return null
    throw err
  }
}
