'use client'

import { forwardRef, useImperativeHandle, useLayoutEffect, useRef, type FormEvent, type KeyboardEvent } from 'react'
import { Button } from '@/components/ui/Button'

export interface ComposerHandle {
  focus: () => void
}

const MAX_HEIGHT = 320

/**
 * The question box: a textarea that grows with the text, Enter sends,
 * Shift+Enter breaks the line. The submit button names the action.
 */
export const Composer = forwardRef<ComposerHandle, {
  value: string
  onChange: (value: string) => void
  onSubmit: (question: string) => void
  busy: boolean
  disabled?: boolean
}>(function Composer({ value, onChange, onSubmit, busy, disabled }, ref) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useImperativeHandle(ref, () => ({ focus: () => textareaRef.current?.focus() }), [])

  useLayoutEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    const next = Math.min(el.scrollHeight, MAX_HEIGHT)
    el.style.height = `${next}px`
    el.style.overflowY = el.scrollHeight > MAX_HEIGHT ? 'auto' : 'hidden'
  }, [value])

  const submit = () => {
    const q = value.trim()
    if (!q || busy || disabled) return
    onSubmit(q)
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      submit()
    }
  }

  const onFormSubmit = (e: FormEvent) => {
    e.preventDefault()
    submit()
  }

  return (
    <form onSubmit={onFormSubmit} aria-label="Fai una domanda">
      <label htmlFor="chiedi-question" className="sr-only">
        La tua domanda
      </label>
      <div className="rounded-lg border border-rule-2 bg-surface p-2 focus-within:border-union focus-within:ring-2 focus-within:ring-union/20">
        <textarea
          id="chiedi-question"
          ref={textareaRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          rows={2}
          disabled={disabled}
          placeholder="Scrivi la domanda, con il contesto che serve: settore, dimensione, Paese."
          aria-describedby="chiedi-question-help"
          className="block min-h-[56px] w-full resize-none bg-transparent px-2 py-1.5 text-read text-ink placeholder:text-ink-3 focus:outline-none disabled:text-ink-3"
        />
        <div className="flex flex-wrap items-center justify-between gap-2 px-1 pt-1">
          <p id="chiedi-question-help" className="text-caption text-ink-3">
            Invio per inviare, Maiusc+Invio per andare a capo.
          </p>
          <Button type="submit" loading={busy} disabled={!value.trim() || disabled}>
            Invia la domanda
          </Button>
        </div>
      </div>
    </form>
  )
})
