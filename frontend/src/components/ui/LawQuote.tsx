import { CheckCircle2, CircleDashed, AlertTriangle, ExternalLink } from 'lucide-react'
import { cn } from '@/lib/cn'
import type { Source, SourceStatus } from '@/lib/sources'
import { SOURCE_STATUS_LABEL } from '@/lib/sources'

function StatusIcon({ status, className }: { status: SourceStatus; className?: string }) {
  if (status === 'verified') return <CheckCircle2 className={cn('h-4 w-4 text-ok', className)} aria-hidden="true" />
  if (status === 'pending') return <CircleDashed className={cn('h-4 w-4 animate-spin text-ink-3', className)} aria-hidden="true" />
  return <AlertTriangle className={cn('h-4 w-4 text-warn', className)} aria-hidden="true" />
}

/**
 * The signature element: a passage of law in Literata, the cited words
 * under the highlighter, the act and article underneath, the verification
 * status and the link to the official text.
 */
export function LawQuote({
  quote,
  before,
  after,
  act,
  article,
  celex,
  url,
  status = 'verified',
  verifiedAt,
  origin,
  className,
}: {
  quote: string
  /** Optional surrounding text, shown un-highlighted. */
  before?: string
  after?: string
  act: string
  article?: string
  celex?: string
  url?: string
  status?: SourceStatus
  verifiedAt?: string
  origin?: string
  className?: string
}) {
  return (
    <figure className={cn('border-l-2 border-mark-deep pl-4', className)}>
      <blockquote className="font-serif text-read leading-relaxed text-ink" lang="it">
        {before && <span className="text-ink-2">{before} </span>}
        <mark>{quote}</mark>
        {after && <span className="text-ink-2"> {after}</span>}
      </blockquote>
      <figcaption className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-small text-ink-2">
        <span>
          <span className="font-medium text-ink">{act}</span>
          {article && <span>, {article}</span>}
        </span>
        {celex && <span className="tabular text-ink-3">CELEX {celex}</span>}
        <span className="inline-flex items-center gap-1" title={verifiedAt ? `${SOURCE_STATUS_LABEL[status]} il ${verifiedAt}` : SOURCE_STATUS_LABEL[status]}>
          <StatusIcon status={status} />
          <span className={cn(status === 'verified' && 'text-ok', status === 'unverified' && 'text-warn')}>
            {status === 'verified' ? 'Verificata' : status === 'pending' ? 'In verifica' : 'Da verificare'}
          </span>
        </span>
        {url && (
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-union hover:underline"
          >
            {origin ?? 'Testo ufficiale'}
            <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
          </a>
        )}
      </figcaption>
    </figure>
  )
}

/** One entry of the sources margin: number, act, article, status, quote. */
export function SourceRow({ source, active, onSelect }: { source: Source; active?: boolean; onSelect?: (id: string) => void }) {
  const Wrapper = onSelect ? 'button' : 'div'
  return (
    <Wrapper
      type={onSelect ? 'button' : undefined}
      onClick={onSelect ? () => onSelect(source.id) : undefined}
      id={`source-${source.id}`}
      className={cn(
        'block w-full rounded-md border-l-2 py-2 pl-3 pr-2 text-left transition-colors',
        active ? 'border-mark-deep bg-mark/20' : 'border-transparent hover:bg-surface-3',
      )}
    >
      <div className="flex items-start gap-2">
        <span className="mt-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded-sm bg-surface-3 px-1 text-caption font-medium tabular text-ink-2">
          {source.index}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-small font-medium text-ink">{source.act}</p>
          {source.article && <p className="text-small text-ink-2">{source.article}</p>}
          {source.quote && (
            <p className="mt-1.5 font-serif text-small leading-relaxed text-ink">
              <mark>{source.quote}</mark>
            </p>
          )}
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-caption">
            <span className="inline-flex items-center gap-1">
              <StatusIcon status={source.status} className="h-3.5 w-3.5" />
              <span className={cn(source.status === 'verified' ? 'text-ok' : source.status === 'unverified' ? 'text-warn' : 'text-ink-3')}>
                {source.status === 'verified' ? 'Verificata' : source.status === 'pending' ? 'In verifica' : 'Da verificare'}
              </span>
            </span>
            {source.celex && <span className="tabular text-ink-3">{source.celex}</span>}
            {source.url && (
              <a
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-union hover:underline"
                onClick={(e) => e.stopPropagation()}
              >
                {source.origin ?? 'Apri'}
                <ExternalLink className="h-3 w-3" aria-hidden="true" />
              </a>
            )}
          </div>
        </div>
      </div>
    </Wrapper>
  )
}
