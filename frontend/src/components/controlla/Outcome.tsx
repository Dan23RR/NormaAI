'use client'

import { useTranslations } from 'next-intl'
import { AlertTriangle, CheckCircle2, CircleSlash, CircleX } from 'lucide-react'
import { Badge } from '@/components/ui/Badge'
import { cn } from '@/lib/cn'
import { GROUP_TEXT, GROUP_TONE, statusLabel } from './labels'
import type { FindingGroup, FindingStatus } from './types'

const GROUP_ICON = {
  correggere: CircleX,
  controllare: AlertTriangle,
  a_posto: CheckCircle2,
  non_coperto: CircleSlash,
} as const

/** The sign of a group. Always next to its words: an icon alone says nothing to a screen reader. */
export function GroupIcon({ group, className }: { group: FindingGroup; className?: string }) {
  const Icon = GROUP_ICON[group]
  return <Icon className={cn('h-4 w-4 shrink-0', GROUP_TEXT[group], className)} aria-hidden="true" />
}

/** The outcome of one reference: icon, words and the tone of its group. */
export function OutcomeBadge({ group, status, className }: { group: FindingGroup; status: FindingStatus; className?: string }) {
  const t = useTranslations()
  return (
    <Badge tone={GROUP_TONE[group]} className={cn('whitespace-normal', className)}>
      <GroupIcon group={group} className="h-3.5 w-3.5" />
      {statusLabel(status, t)}
    </Badge>
  )
}

/** The name of a group as a badge, for the list of checks. */
export function GroupBadge({ group, className }: { group: FindingGroup; className?: string }) {
  const t = useTranslations('controlla.groups')
  return (
    <Badge tone={GROUP_TONE[group]} className={className}>
      <GroupIcon group={group} className="h-3.5 w-3.5" />
      {t(`${group}.label`)}
    </Badge>
  )
}
