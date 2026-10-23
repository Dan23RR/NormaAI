'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { readLegacyLocale, readLocaleCookie, setLocale } from './setLocale'

/**
 * People who chose a language in the previous interface have it only in
 * localStorage. On the first visit without the cookie, the choice is moved
 * to the cookie and the page re-rendered in that language.
 */
export function LocaleSync() {
  const router = useRouter()
  useEffect(() => {
    if (readLocaleCookie()) return
    const legacy = readLegacyLocale()
    if (!legacy || legacy === 'it') return
    setLocale(legacy)
    router.refresh()
  }, [router])
  return null
}
