import type { ReactNode } from 'react'
import { useTranslations } from 'next-intl'
import { cn } from '@/lib/cn'
import type { Translate } from '@/i18n/types'

export type BadgeTone = 'neutral' | 'union' | 'ok' | 'warn' | 'bad' | 'mark'

const toneClasses: Record<BadgeTone, string> = {
  neutral: 'bg-surface-3 text-ink-2',
  union: 'bg-union/10 text-union',
  ok: 'bg-ok/10 text-ok',
  warn: 'bg-warn/10 text-warn',
  bad: 'bg-bad/10 text-bad',
  mark: 'bg-mark text-[#0C1B33]',
}

export function Badge({
  tone = 'neutral',
  children,
  className,
  title,
}: {
  tone?: BadgeTone
  children: ReactNode
  className?: string
  title?: string
}) {
  return (
    <span
      title={title}
      className={cn(
        'inline-flex items-center gap-1 whitespace-nowrap rounded-sm px-2 py-0.5 text-caption font-medium',
        toneClasses[tone],
        className,
      )}
    >
      {children}
    </span>
  )
}

/**
 * The EU frameworks NormaAI covers; the labels live in the `ui.frameworks`
 * messages. `color` is the light value of the `fw-*` token, kept for code
 * that needs a raw colour: the badge itself is drawn with the tokens
 * (FRAMEWORK_CLASSES), which have a dark variant.
 */
export const FRAMEWORK_META: Record<string, { color: string }> = {
  CSRD: { color: '#1B6E4A' },
  CSDDD: { color: '#1A64A8' },
  AI_ACT: { color: '#6D4AB8' },
  DORA: { color: '#A04818' },
  NIS2: { color: '#8A5A00' },
  TAXONOMY: { color: '#0E6B64' },
  GDPR: { color: '#B42A45' },
  CRA: { color: '#9A3D7A' },
  ESRS: { color: '#5B5CA5' },
}

/** Text in the framework hue on its own 10% tint: tokens from globals.css, light and dark. */
const FRAMEWORK_CLASSES: Record<string, string> = {
  CSRD: 'bg-fw-csrd/10 text-fw-csrd',
  CSDDD: 'bg-fw-csddd/10 text-fw-csddd',
  AI_ACT: 'bg-fw-aiact/10 text-fw-aiact',
  DORA: 'bg-fw-dora/10 text-fw-dora',
  NIS2: 'bg-fw-nis2/10 text-fw-nis2',
  TAXONOMY: 'bg-fw-taxonomy/10 text-fw-taxonomy',
  GDPR: 'bg-fw-gdpr/10 text-fw-gdpr',
  CRA: 'bg-fw-cra/10 text-fw-cra',
  ESRS: 'bg-fw-esrs/10 text-fw-esrs',
}

/** "AI Act", "Tassonomia" / "Taxonomy"; an unknown key is shown as it is, without the underscore. */
export function frameworkLabel(key: string, t: Translate): string {
  const path = `ui.frameworks.${key}`
  return key && !key.includes('.') && t.has(path) ? t(path) : key.replace('_', ' ')
}

export function FrameworkBadge({ framework, className }: { framework: string; className?: string }) {
  const t = useTranslations()
  return (
    <span
      className={cn(
        'inline-flex items-center whitespace-nowrap rounded-sm px-2 py-0.5 text-caption font-medium',
        // An unknown framework gets the neutral badge, not an invented hue.
        FRAMEWORK_CLASSES[framework] ?? toneClasses.neutral,
        className,
      )}
    >
      {frameworkLabel(framework, t)}
    </span>
  )
}
