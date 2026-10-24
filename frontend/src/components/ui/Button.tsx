'use client'

import Link from 'next/link'
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { cn } from '@/lib/cn'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
export type ButtonSize = 'sm' | 'md' | 'lg'

const variantClasses: Record<ButtonVariant, string> = {
  primary: 'bg-union text-union-ink hover:bg-union-deep',
  secondary: 'border border-rule-2 bg-surface text-ink hover:bg-surface-2',
  ghost: 'text-ink-2 hover:bg-surface-3 hover:text-ink',
  danger: 'bg-bad text-white hover:bg-bad/90',
}

const sizeClasses: Record<ButtonSize, string> = {
  sm: 'h-8 px-3 text-small',
  md: 'h-10 px-4 text-body',
  lg: 'h-12 px-5 text-read',
}

export function buttonClasses(opts: {
  variant?: ButtonVariant
  size?: ButtonSize
  className?: string
}) {
  return cn(
    'inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-md font-medium no-underline transition-colors',
    'disabled:pointer-events-none disabled:opacity-50',
    variantClasses[opts.variant ?? 'primary'],
    sizeClasses[opts.size ?? 'md'],
    opts.className,
  )
}

export function Spinner({ className }: { className?: string }) {
  return (
    <svg
      className={cn('h-4 w-4 animate-spin', className)}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  )
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  loading?: boolean
  iconLeft?: ReactNode
  iconRight?: ReactNode
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant, size, loading, iconLeft, iconRight, className, children, disabled, type = 'button', ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={buttonClasses({ variant, size, className })}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <Spinner /> : iconLeft}
      {children}
      {!loading && iconRight}
    </button>
  )
})

/** True for links to files served as-is from /public (checkers, PDFs). */
export function isStaticFile(href: string): boolean {
  return /\.(html?|pdf)(?:[?#].*)?$/i.test(href)
}

export function ButtonLink({
  href,
  variant,
  size,
  className,
  iconLeft,
  iconRight,
  children,
  external,
}: {
  href: string
  variant?: ButtonVariant
  size?: ButtonSize
  className?: string
  iconLeft?: ReactNode
  iconRight?: ReactNode
  children: ReactNode
  external?: boolean
}) {
  const classes = buttonClasses({ variant, size, className })
  if (external) {
    return (
      <a href={href} className={classes} target="_blank" rel="noopener noreferrer">
        {iconLeft}
        {children}
        {iconRight}
      </a>
    )
  }
  // Static files in /public are not app routes: a Next <Link> would prefetch
  // them as React Server Component payloads and get a 404.
  if (isStaticFile(href)) {
    return (
      <a href={href} className={classes}>
        {iconLeft}
        {children}
        {iconRight}
      </a>
    )
  }
  return (
    <Link href={href} className={classes}>
      {iconLeft}
      {children}
      {iconRight}
    </Link>
  )
}
