import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

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

/** Canonical short labels and hues for the EU frameworks NormaAI covers. */
export const FRAMEWORK_META: Record<string, { label: string; color: string }> = {
  CSRD: { label: 'CSRD', color: '#1F7A53' },
  CSDDD: { label: 'CSDDD', color: '#1D6FB8' },
  AI_ACT: { label: 'AI Act', color: '#6D4AB8' },
  DORA: { label: 'DORA', color: '#B9541F' },
  NIS2: { label: 'NIS2', color: '#8A5A00' },
  TAXONOMY: { label: 'Tassonomia', color: '#0F766E' },
  GDPR: { label: 'GDPR', color: '#B42A45' },
  CRA: { label: 'CRA', color: '#9A3D7A' },
  ESRS: { label: 'ESRS', color: '#5B5CA5' },
}

export function frameworkLabel(key: string): string {
  return FRAMEWORK_META[key]?.label ?? key.replace('_', ' ')
}

export function FrameworkBadge({ framework, className }: { framework: string; className?: string }) {
  const meta = FRAMEWORK_META[framework] ?? { label: framework, color: '#3D4B61' }
  return (
    <span
      className={cn(
        'inline-flex items-center whitespace-nowrap rounded-sm px-2 py-0.5 text-caption font-medium',
        className,
      )}
      style={{ color: meta.color, backgroundColor: `${meta.color}1A` }}
    >
      {meta.label}
    </span>
  )
}
