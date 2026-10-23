'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/Button'

/**
 * Cookie banner informativo (no opt-in gate).
 *
 * NormaAI usa SOLO cookie/storage tecnici di prima parte (token di sessione
 * JWT in localStorage, preferenza lingua e tema, stato UI) e NESSUN cookie
 * di analytics o marketing di terze parti. Ai sensi della Direttiva ePrivacy
 * e del Provvedimento del Garante 231/2021, i cookie strettamente tecnici
 * sono esenti dal consenso preventivo: basta un'informativa con link alla
 * cookie policy, senza pulsanti accetta/rifiuta.
 *
 * NOTA: se si aggiungono strumenti di terze parti (analytics con cookie,
 * pixel), questo banner va trasformato in un consent manager con opt-in
 * granulare PRIMA di caricare gli script di tracciamento.
 */

const DISMISS_KEY = 'normaai.cookie-banner.dismissed'

export function CookieBanner() {
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
    <div role="region" aria-label="Informativa cookie" className="fixed inset-x-0 bottom-0 z-40 px-4 pb-4 sm:px-6">
      <div className="mx-auto flex max-w-3xl flex-col gap-3 rounded-lg border border-rule bg-surface p-4 shadow-pop sm:flex-row sm:items-center sm:gap-5">
        <p className="text-small text-ink-2">
          Usiamo solo cookie tecnici necessari al funzionamento del sito (sessione, lingua, preferenze).
          Nessun cookie di profilazione o di terze parti. Dettagli nella{' '}
          <Link href="/cookie" className="text-union hover:underline">
            cookie policy
          </Link>
          .
        </p>
        <Button size="sm" variant="secondary" onClick={dismiss} className="shrink-0">
          Ho capito
        </Button>
      </div>
    </div>
  )
}
