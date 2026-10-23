/**
 * The corpus date of a `/api/v1/qa` response. The backend puts it in the
 * envelope's `metadata.corpus_as_of` when configured (src/api/routers/
 * intelligence.py); the demo keeps an example date in the data itself.
 * The date is shown through `formatCorpusDate` in src/i18n/format.ts.
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
