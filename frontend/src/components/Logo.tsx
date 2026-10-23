import Link from 'next/link'
import { cn } from '@/lib/cn'

/**
 * The brand: an ink square with a yellow highlighter stroke and the N,
 * plus the wordmark in Literata with the same stroke behind "Norma".
 */
export function LogoMark({ className, size = 28 }: { className?: string; size?: number }) {
  return (
    <svg
      viewBox="0 0 64 64"
      width={size}
      height={size}
      className={cn('shrink-0', className)}
      aria-hidden="true"
      focusable="false"
    >
      <rect width="64" height="64" rx="14" fill="#0C1B33" />
      <rect x="9" y="34" width="46" height="11" rx="3" fill="#F5C400" transform="rotate(-3 32 39.5)" />
      <path
        d="M20 47V17l24 30V17"
        fill="none"
        stroke="#FFFFFF"
        strokeWidth="6.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn('font-serif font-semibold tracking-tight text-ink', className)}>
      <span className="relative isolate">
        <span
          aria-hidden="true"
          className="absolute inset-x-[-0.05em] bottom-[0.08em] -z-10 h-[0.42em] -rotate-1 rounded-[2px] bg-mark"
        />
        Norma
      </span>
      AI
    </span>
  )
}

export function Logo({
  href = '/',
  size = 'md',
  className,
}: {
  href?: string
  size?: 'sm' | 'md' | 'lg'
  className?: string
}) {
  const mark = size === 'lg' ? 36 : size === 'sm' ? 24 : 28
  const text = size === 'lg' ? 'text-h2' : size === 'sm' ? 'text-h4' : 'text-h3'
  return (
    <Link
      href={href}
      className={cn('inline-flex items-center gap-2.5 no-underline', className)}
      aria-label="NormaAI, pagina iniziale"
    >
      <LogoMark size={mark} />
      <Wordmark className={text} />
    </Link>
  )
}
