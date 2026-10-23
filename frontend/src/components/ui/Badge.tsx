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

/** Hues of the EU frameworks NormaAI covers; the labels live in the `ui.frameworks` messages. */
export const FRAMEWORK_META: Record<string, { color: string }> = {
  CSRD: { color: '#1F7A53' },
  CSDDD: { color: '#1D6FB8' },
  AI_ACT: { color: '#6D4AB8' },
  DORA: { color: '#B9541F' },
  NIS2: { color: '#8A5A00' },
  TAXONOMY: { color: '#0F766E' },
  GDPR: { color: '#B42A45' },
  CRA: { color: '#9A3D7A' },
  ESRS: { color: '#5B5CA5' },
}

/** "AI Act", "Tassonomia" / "Taxonomy"; an unknown key is shown as it is, without the underscore. */
export function frameworkLabel(key: string, t: Translate): string {
  const path = `ui.frameworks.${key}`
  return key && !key.includes('.') && t.has(path) ? t(path) : key.replace('_', ' ')
}

export function FrameworkBadge({ framework, className }: { framework: string; className?: string }) {
  const t = useTranslations()
  const color = FRAMEWORK_META[framework]?.color ?? '#3D4B61'
  return (
    <span
      className={cn(
        'inline-flex items-center whitespace-nowrap rounded-sm px-2 py-0.5 text-caption font-medium',
        className,
      )}
      style={{ color, backgroundColor: `${color}1A` }}
    >
      {frameworkLabel(framework, t)}
    </span>
  )
}
