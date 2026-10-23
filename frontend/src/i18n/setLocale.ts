'use client'

import { useCallback } from 'react'
import { useRouter } from 'next/navigation'
import {
  LOCALE_COOKIE,
  LOCALE_COOKIE_MAX_AGE,
  LOCALE_STORAGE_KEY,
  isLanguage,
  type Language,
} from './config'
import { QA_LANGUAGE_KEY } from '@/lib/chiedi/storage'

/**
 * Remember the chosen language: the cookie the server reads (one year,
 * SameSite=Lax) and the localStorage key the previous interface used. The
 * per-question override of the answer language (Chiedi) is cleared, so
 * the answers follow the interface again.
 */
export function setLocale(language: Language): void {
  if (typeof document === 'undefined') return
  document.cookie = `${LOCALE_COOKIE}=${language}; path=/; max-age=${LOCALE_COOKIE_MAX_AGE}; SameSite=Lax`
  try {
    localStorage.setItem(LOCALE_STORAGE_KEY, language)
    localStorage.removeItem(QA_LANGUAGE_KEY)
  } catch {
    /* the cookie is enough */
  }
}

/** The language of the cookie, if any. */
export function readLocaleCookie(): Language | null {
  if (typeof document === 'undefined') return null
  const match = document.cookie.match(new RegExp(`(?:^|;\\s*)${LOCALE_COOKIE.replace('.', '\\.')}=([^;]*)`))
  const value = match ? decodeURIComponent(match[1]) : null
  return isLanguage(value) ? value : null
}

/** The language the previous interface saved in localStorage, if any. */
export function readLegacyLocale(): Language | null {
  try {
    const value = localStorage.getItem(LOCALE_STORAGE_KEY)
    return isLanguage(value) ? value : null
  } catch {
    return null
  }
}

/** Saves the language and re-renders the page in it. */
export function useSetLocale(): (language: Language) => void {
  const router = useRouter()
  return useCallback(
    (language: Language) => {
      setLocale(language)
      router.refresh()
    },
    [router],
  )
}
