'use client'

import { useMemo } from 'react'
import { useLocale, useTranslations } from 'next-intl'
import type { TextContext } from './types'

/** The locale and the root translator, for the libraries that build text (scope rules, calendar, clipboard). */
export function useTextContext(): TextContext {
  const locale = useLocale()
  const t = useTranslations()
  return useMemo(() => ({ locale, t }), [locale, t])
}
