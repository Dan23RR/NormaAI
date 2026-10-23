'use client'

import {
  forwardRef,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react'
import { cn } from '@/lib/cn'

const controlClasses =
  'w-full rounded-md border border-rule-2 bg-surface px-3 text-body text-ink placeholder:text-ink-3 transition-colors ' +
  'focus:border-union focus:outline-none focus:ring-2 focus:ring-union/20 ' +
  'disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-ink-3 ' +
  'aria-[invalid=true]:border-bad aria-[invalid=true]:focus:ring-bad/20'

/**
 * Label, control, help and error in one block. Pass `htmlFor` matching the
 * control id; the help and error ids are derived from it so the control can
 * reference them with aria-describedby={describedBy(id, { help, error })}.
 */
export function Field({
  label,
  htmlFor,
  help,
  error,
  required,
  children,
  className,
}: {
  label: string
  htmlFor: string
  help?: ReactNode
  error?: string
  required?: boolean
  children: ReactNode
  className?: string
}) {
  return (
    <div className={cn('space-y-1.5', className)}>
      <label htmlFor={htmlFor} className="block text-small font-medium text-ink">
        {label}
        {required && (
          <span className="text-bad" aria-hidden="true">
            {' '}
            *
          </span>
        )}
      </label>
      {children}
      {error ? (
        <p id={`${htmlFor}-error`} className="text-caption text-bad" role="alert">
          {error}
        </p>
      ) : help ? (
        <p id={`${htmlFor}-help`} className="text-caption text-ink-3">
          {help}
        </p>
      ) : null}
    </div>
  )
}

export function describedBy(id: string, opts: { help?: ReactNode; error?: string }) {
  if (opts.error) return `${id}-error`
  if (opts.help) return `${id}-help`
  return undefined
}

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { className, invalid, ...rest },
  ref,
) {
  return (
    <input
      ref={ref}
      className={cn('h-10', controlClasses, className)}
      aria-invalid={invalid || undefined}
      {...rest}
    />
  )
})

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  invalid?: boolean
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { className, invalid, children, ...rest },
  ref,
) {
  return (
    <select
      ref={ref}
      className={cn('h-10 appearance-none bg-no-repeat pr-9', controlClasses, className)}
      style={{
        backgroundImage:
          "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%236B7788' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E\")",
        backgroundPosition: 'right 0.75rem center',
      }}
      aria-invalid={invalid || undefined}
      {...rest}
    >
      {children}
    </select>
  )
})

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  invalid?: boolean
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { className, invalid, ...rest },
  ref,
) {
  return (
    <textarea
      ref={ref}
      className={cn('min-h-[96px] py-2.5', controlClasses, className)}
      aria-invalid={invalid || undefined}
      {...rest}
    />
  )
})

export function Checkbox({
  id,
  label,
  description,
  className,
  ...rest
}: InputHTMLAttributes<HTMLInputElement> & { id: string; label: ReactNode; description?: ReactNode }) {
  return (
    <label htmlFor={id} className={cn('flex cursor-pointer items-start gap-3', className)}>
      <input
        id={id}
        type="checkbox"
        className="mt-0.5 h-4 w-4 shrink-0 rounded-sm border-rule-2 text-union focus:ring-union/30"
        {...rest}
      />
      <span className="text-body text-ink">
        {label}
        {description && <span className="block text-caption text-ink-3">{description}</span>}
      </span>
    </label>
  )
}
