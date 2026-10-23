/**
 * "2026-10-01" (or a full ISO timestamp) as "1 ottobre 2026". A value that
 * is not a date comes back as it is: the page never invents a date, but it
 * does not hide what the backend sent either.
 */
export function formatItalianDate(value: string | null | undefined): string | undefined {
  if (typeof value !== 'string') return undefined
  const trimmed = value.trim()
  if (!trimmed) return undefined
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(trimmed)
  if (!m) return trimmed
  const date = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])))
  if (Number.isNaN(date.getTime())) return trimmed
  try {
    return new Intl.DateTimeFormat('it-IT', {
      day: 'numeric',
      month: 'long',
      year: 'numeric',
      timeZone: 'UTC',
    }).format(date)
  } catch {
    return trimmed
  }
}

/**
 * The corpus date of a `/api/v1/qa` response. The backend puts it in the
 * envelope's `metadata.corpus_as_of` when configured (src/api/routers/
 * intelligence.py); the demo keeps an example date in the data itself.
 */
export function corpusDateFrom(
  metadata: Record<string, unknown> | undefined,
  data: { corpus_as_of?: string } | undefined,
): string | undefined {
  const fromMeta = metadata?.corpus_as_of
  if (typeof fromMeta === 'string' && fromMeta.trim()) return fromMeta.trim()
  const fromData = data?.corpus_as_of
  if (typeof fromData === 'string' && fromData.trim()) return fromData.trim()
  return undefined
}
