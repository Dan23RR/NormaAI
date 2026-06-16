'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Cookie, X } from 'lucide-react'

/**
 * Cookie banner informativo (no opt-in gate).
 *
 * NormaAI usa SOLO cookie/storage tecnici di prima parte (token di sessione
 * JWT in localStorage, preferenza lingua, stato UI della dashboard) e NESSUN
 * cookie di analytics o marketing di terze parti. Ai sensi della Direttiva
 * ePrivacy e del Provvedimento del Garante 231/2021, i cookie strettamente
 * tecnici sono esenti dal consenso preventivo: è quindi sufficiente
 * un'informativa con link alla cookie policy, senza pulsanti accetta/rifiuta.
 *
 * NOTA per il futuro: se si aggiungono Google Analytics / GTM / pixel o altri
 * strumenti di terze parti, questo banner va trasformato in un consent manager
 * con opt-in granulare (accetta / rifiuta non essenziali) PRIMA di caricare
 * gli script di tracciamento.
 */

const DISMISS_KEY = 'normaai.cookie-banner.dismissed'

export function CookieBanner() {
  // Parte nascosto: lo mostriamo solo dopo aver verificato lo storage lato
  // client, così evitiamo flicker in SSR e non lampeggia a chi l'ha già chiuso.
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    try {
      if (localStorage.getItem(DISMISS_KEY) !== 'true') {
        setVisible(true)
      }
    } catch {
      // Storage non disponibile (private mode / SSR edge): mostra comunque
      // l'informativa, è la scelta più prudente.
      setVisible(true)
    }
  }, [])

  const dismiss = () => {
    try {
      localStorage.setItem(DISMISS_KEY, 'true')
    } catch {
      /* ignore — la chiusura resta comunque effettiva per la sessione */
    }
    setVisible(false)
  }

  if (!visible) return null

  return (
    <div
      role="dialog"
      aria-live="polite"
      aria-label="Informativa cookie"
      className="fixed inset-x-0 bottom-0 z-50 px-4 pb-4 sm:px-6"
    >
      <div className="mx-auto flex max-w-3xl flex-col gap-3 rounded-xl border border-line bg-white/95 p-4 shadow-[0_12px_32px_-8px_rgba(20,20,19,0.18)] backdrop-blur sm:flex-row sm:items-center sm:gap-4">
        <div className="flex items-start gap-3">
          <div className="hidden h-9 w-9 shrink-0 items-center justify-center rounded-md bg-clay-soft text-clay sm:inline-flex">
            <Cookie className="h-5 w-5" />
          </div>
          <p className="text-sm leading-relaxed text-night-2">
            Usiamo <strong className="text-night">solo cookie tecnici</strong> necessari al
            funzionamento del sito (sessione, lingua, preferenze). Nessun cookie di profilazione o
            di terze parti. Dettagli nella{' '}
            <Link
              href="/cookie"
              className="font-medium text-clay underline-offset-4 hover:text-clay-deep hover:underline"
            >
              cookie policy
            </Link>
            .
          </p>
        </div>
        <button
          type="button"
          onClick={dismiss}
          className="inline-flex shrink-0 items-center justify-center gap-1.5 self-stretch rounded-md bg-night px-4 py-2 text-sm font-medium text-paper transition hover:bg-coal-2 sm:self-auto"
        >
          Ho capito
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  )
}
