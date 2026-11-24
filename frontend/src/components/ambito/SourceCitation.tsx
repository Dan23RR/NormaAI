'use client'

import { useTranslations } from 'next-intl'
import { AlertTriangle, CheckCircle2, ExternalLink } from 'lucide-react'
import { FRAMEWORK_META } from '@/components/ui/Badge'
import { cn } from '@/lib/cn'
import { useTextContext } from '@/i18n/useTextContext'
import { verificationLabel, type ScopeSource } from '@/lib/scope/sources'
import type { Source } from '@/lib/sources'

/** The tag of a rule set or of a calendar entry: the hue of its framework when it has one, neutral otherwise. */
export function FrameworkTag({ framework, label, className }: { framework: string; label: string; className?: string }) {
  const color = FRAMEWORK_META[framework]?.color ?? '#3D4B61'
  return (
    <span
      className={cn('inline-flex items-center whitespace-nowrap rounded-sm px-2 py-0.5 text-caption font-medium', className)}
      style={{ color, backgroundColor: `${color}1A` }}
    >
      {label}
    </span>
  )
}

/**
 * What the last check against the official text says about a source:
 * "Verificata il <date>" only when that check found the passage, with its
 * date; "Fonte indicata, non ancora verificata" in every other case.
 */
export function VerificationMark({ source, className }: { source: Source; className?: string }) {
  const ctx = useTextContext()
  const verified = source.status === 'verified' && Boolean(source.verifiedAt)
  const Icon = verified ? CheckCircle2 : AlertTriangle
  return (
    <span className={cn('inline-flex items-start gap-1', verified ? 'text-ok' : 'text-warn', className)}>
      <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      <span>{verificationLabel(source, ctx)}</span>
    </span>
  )
}

/** The verified passage, in the language of the official text, under the highlighter. */
export function SourcePassage({ source, className }: { source: Source; className?: string }) {
  if (source.status !== 'verified' || !source.quote) return null
  const lang = (source as ScopeSource).quoteLang ?? 'it'
  return (
    <blockquote
      lang={lang}
      className={cn('border-l-2 border-mark-deep pl-3 font-serif text-small leading-relaxed text-ink', className)}
    >
      <mark>{source.quote}</mark>
    </blockquote>
  )
}

/** Act, article, CELEX and the link to the official text, on one wrapping line. */
export function SourceReference({ source, numbered }: { source: Source; numbered?: boolean }) {
  const tu = useTranslations('ui')
  return (
    <span className="text-small leading-relaxed text-ink-2">
      {numbered && <span className="mr-1.5 tabular text-ink-3">[{source.index}]</span>}
      <span className="font-medium text-ink">{source.act}</span>
      {source.article && <span>, {source.article}</span>}
      {source.celex && <span className="ml-2 whitespace-nowrap tabular text-ink-3">{tu('celex', { celex: source.celex })}</span>}
      {source.url && (
        <a
          href={source.url}
          target="_blank"
          rel="noopener noreferrer"
          className="ml-2 inline-flex items-center gap-1 whitespace-nowrap text-union hover:underline"
        >
          {source.origin ?? tu('officialText')}
          <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
        </a>
      )}
    </span>
  )
}

/** One entry of a legal basis: the reference, what the last check found, the passage. */
export function SourceEntry({ source }: { source: Source }) {
  return (
    <li className="space-y-1">
      <SourceReference source={source} numbered />
      <VerificationMark source={source} className="flex text-caption" />
      <SourcePassage source={source} />
    </li>
  )
}
