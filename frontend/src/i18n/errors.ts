'use client'

import { useCallback } from 'react'
import { useTranslations } from 'next-intl'
import { ApiError } from '@/lib/api-error'
import type { Translate } from './types'

/**
 * The text to show for a failure: the server's own detail when there is
 * one, the translated message of an API error code otherwise, the message
 * of any other error, and the fallback when nothing better is known.
 */
export function errorText(err: unknown, t: Translate, fallbackKey = 'errors.generic'): string {
  if (err instanceof ApiError) return err.detail ?? t(`errors.${err.code}`, err.values)
  if (err instanceof Error && err.message) return err.message
  return t(fallbackKey)
}

export function useErrorText(): (err: unknown, fallbackKey?: string) => string {
  const t = useTranslations()
  return useCallback((err: unknown, fallbackKey?: string) => errorText(err, t, fallbackKey), [t])
}
