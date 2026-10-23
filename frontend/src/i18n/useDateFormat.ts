'use client'

import { useCallback } from 'react'
import { useFormatter, useTranslations } from 'next-intl'
import { LONG_DATE, MONTH_YEAR, isoToUtcDate, quarterOf, type DatePrecision } from './format'

/**
 * ISO dates as the reader expects them, through next-intl's formatter:
 * "2 agosto 2026" / "2 August 2026", "luglio 2029" / "July 2029",
 * "primo trimestre 2027" / "Q1 2027".
 */
export function useDateFormat(): (iso: string, precision?: DatePrecision) => string {
  const format = useFormatter()
  const t = useTranslations('ui.dates')
  return useCallback(
    (iso: string, precision: DatePrecision = 'day') => {
      const date = isoToUtcDate(iso)
      if (!date) return iso
      if (precision === 'day') return format.dateTime(date, LONG_DATE)
      if (precision === 'month') return format.dateTime(date, MONTH_YEAR)
      return t('quarter', { quarter: String(quarterOf(date)), year: String(date.getUTCFullYear()) })
    },
    [format, t],
  )
}
