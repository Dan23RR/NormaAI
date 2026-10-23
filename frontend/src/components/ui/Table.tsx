import type { HTMLAttributes, TdHTMLAttributes, ThHTMLAttributes } from 'react'
import { cn } from '@/lib/cn'

/** Horizontal rules, no zebra, numbers right-aligned and tabular. */
export function Table({ className, children, ...rest }: HTMLAttributes<HTMLTableElement>) {
  return (
    <div className="overflow-x-auto rounded-lg border border-rule bg-surface">
      <table className={cn('w-full border-collapse text-body', className)} {...rest}>
        {children}
      </table>
    </div>
  )
}

export function THead({ children }: { children: React.ReactNode }) {
  return <thead className="bg-surface-2">{children}</thead>
}

export function TBody({ children }: { children: React.ReactNode }) {
  return <tbody>{children}</tbody>
}

export function TR({ className, children, ...rest }: HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr className={cn('border-b border-rule last:border-b-0', className)} {...rest}>
      {children}
    </tr>
  )
}

export function TH({
  numeric,
  className,
  children,
  ...rest
}: ThHTMLAttributes<HTMLTableCellElement> & { numeric?: boolean }) {
  return (
    <th
      scope="col"
      className={cn(
        'px-4 py-2.5 text-small font-medium text-ink-2',
        numeric ? 'text-right tabular' : 'text-left',
        className,
      )}
      {...rest}
    >
      {children}
    </th>
  )
}

export function TD({
  numeric,
  className,
  children,
  ...rest
}: TdHTMLAttributes<HTMLTableCellElement> & { numeric?: boolean }) {
  return (
    <td
      className={cn('px-4 py-3 align-top text-ink', numeric ? 'text-right tabular' : 'text-left', className)}
      {...rest}
    >
      {children}
    </td>
  )
}
