'use client'

import { useId, useRef, type KeyboardEvent } from 'react'
import { cn } from '@/lib/cn'

export interface TabItem {
  id: string
  label: string
  count?: number
}

/** Underline tabs with roving focus (arrow keys, Home, End). */
export function Tabs({
  tabs,
  value,
  onChange,
  label,
  className,
}: {
  tabs: TabItem[]
  value: string
  onChange: (id: string) => void
  label: string
  className?: string
}) {
  const baseId = useId()
  const refs = useRef<Array<HTMLButtonElement | null>>([])

  const onKeyDown = (e: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const last = tabs.length - 1
    let next: number | null = null
    if (e.key === 'ArrowRight') next = index === last ? 0 : index + 1
    if (e.key === 'ArrowLeft') next = index === 0 ? last : index - 1
    if (e.key === 'Home') next = 0
    if (e.key === 'End') next = last
    if (next === null) return
    e.preventDefault()
    refs.current[next]?.focus()
    onChange(tabs[next].id)
  }

  return (
    <div role="tablist" aria-label={label} className={cn('flex gap-1 border-b border-rule', className)}>
      {tabs.map((tab, i) => {
        const selected = tab.id === value
        return (
          <button
            key={tab.id}
            ref={(el) => {
              refs.current[i] = el
            }}
            role="tab"
            type="button"
            id={`${baseId}-${tab.id}`}
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(tab.id)}
            onKeyDown={(e) => onKeyDown(e, i)}
            className={cn(
              '-mb-px inline-flex h-10 items-center gap-2 border-b-2 px-3 text-body transition-colors',
              selected
                ? 'border-union font-medium text-ink'
                : 'border-transparent text-ink-2 hover:border-rule-2 hover:text-ink',
            )}
          >
            {tab.label}
            {typeof tab.count === 'number' && (
              <span className="rounded-sm bg-surface-3 px-1.5 text-caption tabular text-ink-2">{tab.count}</span>
            )}
          </button>
        )
      })}
    </div>
  )
}
