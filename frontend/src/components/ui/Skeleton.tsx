import { useTranslations } from 'next-intl'
import { cn } from '@/lib/cn'

export function Skeleton({ className, label }: { className?: string; label?: string }) {
  const t = useTranslations('ui')
  const text = label ?? t('loading')
  return (
    <div className={cn('animate-pulse rounded-md bg-surface-3', className)} role="status" aria-label={text}>
      <span className="sr-only">{text}</span>
    </div>
  )
}

export function SkeletonText({ lines = 3, className }: { lines?: number; className?: string }) {
  const t = useTranslations('ui')
  const widths = ['w-full', 'w-11/12', 'w-4/5', 'w-2/3']
  return (
    <div className={cn('space-y-2', className)} role="status" aria-label={t('loading')}>
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className={cn('h-3.5 animate-pulse rounded-sm bg-surface-3', widths[i % widths.length])} />
      ))}
      <span className="sr-only">{t('loading')}</span>
    </div>
  )
}
