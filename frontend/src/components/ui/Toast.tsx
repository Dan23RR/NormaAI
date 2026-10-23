'use client'

import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react'
import { CheckCircle2, AlertTriangle, Info, X } from 'lucide-react'
import { cn } from '@/lib/cn'

export type ToastKind = 'ok' | 'bad' | 'neutral'

interface ToastItem {
  id: number
  kind: ToastKind
  title: string
  description?: string
}

interface ToastApi {
  toast: (t: { kind?: ToastKind; title: string; description?: string; durationMs?: number }) => void
}

const ToastContext = createContext<ToastApi | null>(null)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const counter = useRef(0)

  const dismiss = useCallback((id: number) => {
    setItems((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const toast = useCallback<ToastApi['toast']>(
    ({ kind = 'neutral', title, description, durationMs = 5000 }) => {
      const id = ++counter.current
      setItems((prev) => [...prev, { id, kind, title, description }])
      if (durationMs > 0) window.setTimeout(() => dismiss(id), durationMs)
    },
    [dismiss],
  )

  const api = useMemo(() => ({ toast }), [toast])

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        className="pointer-events-none fixed inset-x-4 bottom-4 z-50 flex flex-col items-end gap-2 sm:inset-x-auto sm:right-6"
        role="status"
        aria-live="polite"
      >
        {items.map((t) => (
          <div
            key={t.id}
            className={cn(
              'pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-lg border bg-surface px-4 py-3 shadow-pop',
              t.kind === 'ok' && 'border-ok/30',
              t.kind === 'bad' && 'border-bad/30',
              t.kind === 'neutral' && 'border-rule',
            )}
          >
            <span className={cn('mt-0.5 shrink-0', t.kind === 'ok' && 'text-ok', t.kind === 'bad' && 'text-bad', t.kind === 'neutral' && 'text-union')}>
              {t.kind === 'ok' ? (
                <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
              ) : t.kind === 'bad' ? (
                <AlertTriangle className="h-4 w-4" aria-hidden="true" />
              ) : (
                <Info className="h-4 w-4" aria-hidden="true" />
              )}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-body font-medium text-ink">{t.title}</p>
              {t.description && <p className="mt-0.5 text-small text-ink-2">{t.description}</p>}
            </div>
            <button
              type="button"
              onClick={() => dismiss(t.id)}
              className="-mr-1 -mt-1 rounded-md p-1 text-ink-3 hover:bg-surface-3 hover:text-ink"
              aria-label="Chiudi la notifica"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within ToastProvider')
  return ctx
}
