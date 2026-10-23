'use client'

import { useEffect, useRef, type ReactNode } from 'react'
import { X } from 'lucide-react'
import { cn } from '@/lib/cn'

/**
 * Modal built on the native <dialog>: focus trap, Escape and the inert
 * background come from the platform. Click on the backdrop closes it.
 */
export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  size = 'md',
}: {
  open: boolean
  onClose: () => void
  title: string
  description?: ReactNode
  children: ReactNode
  footer?: ReactNode
  size?: 'sm' | 'md' | 'lg'
}) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (open && !el.open) el.showModal()
    if (!open && el.open) el.close()
  }, [open])

  const width = size === 'lg' ? 'max-w-2xl' : size === 'sm' ? 'max-w-sm' : 'max-w-lg'

  return (
    <dialog
      ref={ref}
      onCancel={(e) => {
        e.preventDefault()
        onClose()
      }}
      onClick={(e) => {
        if (e.target === ref.current) onClose()
      }}
      aria-labelledby="dialog-title"
      className={cn(
        'w-[calc(100%-2rem)] rounded-xl border border-rule bg-surface p-0 text-ink shadow-pop backdrop:bg-[#0C1B33]/50',
        width,
      )}
    >
      <div className="flex items-start justify-between gap-4 px-6 pt-6">
        <div>
          <h2 id="dialog-title" className="text-h3">
            {title}
          </h2>
          {description && <p className="mt-1 text-small text-ink-2">{description}</p>}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="-mr-2 -mt-2 rounded-md p-2 text-ink-3 hover:bg-surface-3 hover:text-ink"
          aria-label="Chiudi"
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
      <div className="px-6 py-5">{children}</div>
      {footer && <div className="flex items-center justify-end gap-2 border-t border-rule px-6 py-4">{footer}</div>}
    </dialog>
  )
}
