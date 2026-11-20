'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { Check, Copy } from 'lucide-react'
import { copyText } from '@/components/ambito/clipboard'
import { buttonClasses } from '@/components/ui/Button'
import { cn } from '@/lib/cn'

export const CONTACT_EMAIL = 'info@normaai.org'

/**
 * The contact address in clear, with a button that copies it. A mailto link
 * does nothing on a computer without a mail client, so next to every
 * "write to us" button the address can be read and copied on its own.
 */
export function EmailCopy({ lead, className }: { lead?: string; className?: string }) {
  const t = useTranslations('site.contact')
  const [state, setState] = useState<'idle' | 'copied' | 'failed'>('idle')

  const copy = async () => setState((await copyText(CONTACT_EMAIL)) ? 'copied' : 'failed')

  return (
    <div className={cn('text-small text-ink-2', className)}>
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
        {lead && <span>{lead}</span>}
        <a href={`mailto:${CONTACT_EMAIL}`} className="font-medium text-union underline hover:no-underline">
          {CONTACT_EMAIL}
        </a>
        <button type="button" onClick={copy} className={buttonClasses({ variant: 'ghost', size: 'sm' })}>
          {state === 'copied' ? (
            <Check className="h-3.5 w-3.5" aria-hidden="true" />
          ) : (
            <Copy className="h-3.5 w-3.5" aria-hidden="true" />
          )}
          {state === 'copied' ? t('copied') : t('copy')}
        </button>
      </p>
      <p role="status" className={state === 'failed' ? 'mt-1 text-caption text-bad' : 'sr-only'}>
        {state === 'copied' ? t('copied') : state === 'failed' ? t('failed') : ''}
      </p>
    </div>
  )
}
