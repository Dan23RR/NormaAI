'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { Button } from '@/components/ui/Button'

/**
 * Cookie notice, informative only (no opt-in gate).
 *
 * NormaAI uses ONLY first-party technical storage (one language cookie, the
 * session tokens and the interface preferences in localStorage) and NO
 * third-party analytics or marketing cookie. Under the ePrivacy Directive and
 * Decision 231/2021 of the Italian data protection authority, strictly
 * technical storage is exempt from prior consent: a notice with a link to the
 * cookie policy is enough, without accept and reject buttons.
 *
 * NOTE: if third-party tools are added (analytics with cookies, pixels), this
 * notice must become a consent manager with granular opt-in BEFORE any
 * tracking script is loaded.
 *
 * Placement. The notice never sits on page content. On small screens it is a
 * plain block in the flow, at the end of the document (a fixed bar there
 * covered the last controls of a page, for example the demo button of the
 * sign-in page on a 390 x 844 phone). From the `sm` breakpoint it is sticky
 * at the bottom of the viewport: it stays in view while reading, and since it
 * still takes its own space at the end of the document, the last lines of the
 * page can always be scrolled clear of it.
 */

const DISMISS_KEY = 'normaai.cookie-banner.dismissed'

export function CookieBanner() {
  const t = useTranslations('ui.cookieBanner')
  // Hidden until the client confirms the storage state: no SSR flicker and
  // no flash for people who already closed it.
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    try {
      if (localStorage.getItem(DISMISS_KEY) !== 'true') setVisible(true)
    } catch {
      setVisible(true)
    }
  }, [])

  const dismiss = () => {
    try {
      localStorage.setItem(DISMISS_KEY, 'true')
    } catch {
      /* the dismissal still holds for this session */
    }
    setVisible(false)
  }

  if (!visible) return null

  return (
    <div
      role="region"
      aria-label={t('label')}
      className="border-t border-rule bg-surface sm:pointer-events-none sm:sticky sm:bottom-0 sm:z-40 sm:border-t-0 sm:bg-transparent sm:px-6 sm:pb-4 sm:pt-2"
    >
      <div className="mx-auto flex max-w-3xl flex-col gap-3 px-4 py-4 sm:pointer-events-auto sm:flex-row sm:items-center sm:gap-5 sm:rounded-lg sm:border sm:border-rule sm:bg-surface sm:p-4 sm:shadow-pop">
        <p className="text-small text-ink-2">
          {t.rich('text', {
            link: (chunks) => (
              <Link href="/cookie" className="text-union underline hover:no-underline">
                {chunks}
              </Link>
            ),
          })}
        </p>
        <Button size="sm" variant="secondary" onClick={dismiss} className="shrink-0 self-start sm:self-auto">
          {t('ok')}
        </Button>
      </div>
    </div>
  )
}
