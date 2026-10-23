'use client'

import { useEffect, useState, type ReactNode } from 'react'
import { Field, Input, describedBy } from '@/components/ui/Field'
import { cn } from '@/lib/cn'
import { formatInt, parseItNumber } from '@/lib/scope/format'

/**
 * A numeric field that accepts Italian notation ("1.200", "450.000.000",
 * "1,5") and shows thousands separators when it loses focus. The parent
 * keeps the number; the text is local.
 */
export function NumberField({
  id,
  label,
  help,
  value,
  onChange,
  placeholder,
  suffix,
  required,
  className,
}: {
  id: string
  label: string
  help?: ReactNode
  value: number | null
  onChange: (value: number | null) => void
  placeholder?: string
  suffix?: string
  required?: boolean
  className?: string
}) {
  const [text, setText] = useState(value == null ? '' : formatInt(value))
  const [focused, setFocused] = useState(false)
  const [error, setError] = useState<string | undefined>()

  useEffect(() => {
    if (!focused) {
      setText(value == null ? '' : formatInt(value))
      if (value != null) setError(undefined)
    }
  }, [value, focused])

  return (
    <Field label={label} htmlFor={id} help={help} error={error} required={required} className={className}>
      <div className="relative">
        <Input
          id={id}
          inputMode="decimal"
          autoComplete="off"
          value={text}
          placeholder={placeholder}
          invalid={!!error}
          aria-describedby={describedBy(id, { help, error })}
          className={cn(suffix && (suffix.length > 3 ? 'pr-24' : 'pr-9'))}
          onFocus={() => setFocused(true)}
          onChange={(e) => {
            const raw = e.target.value
            setText(raw)
            if (raw.trim() === '') {
              setError(undefined)
              onChange(null)
              return
            }
            const n = parseItNumber(raw)
            if (n == null || n < 0) {
              setError('Inserisci un numero, per esempio 1.200.')
              onChange(null)
            } else {
              setError(undefined)
              onChange(n)
            }
          }}
          onBlur={() => {
            setFocused(false)
            if (value != null) setText(formatInt(value))
          }}
        />
        {suffix && (
          <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-small text-ink-3">
            {suffix}
          </span>
        )}
      </div>
    </Field>
  )
}
