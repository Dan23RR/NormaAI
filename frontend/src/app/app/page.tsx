'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { ListChecks, CalendarClock, Building2, ArrowRight } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { Button } from '@/components/ui/Button'
import { itemKeys } from '@/components/LegalLayout'

const TILES = [
  { key: 'ambito', href: '/app/ambito', icon: ListChecks },
  { key: 'monitoraggio', href: '/app/monitoraggio', icon: CalendarClock },
  { key: 'clienti', href: '/app/clienti', icon: Building2 },
] as const

export default function AppHome() {
  const t = useTranslations('app.home')
  const tc = useTranslations('chiedi')
  const router = useRouter()
  const { user } = useAuth()
  const [question, setQuestion] = useState('')

  const ask = (q: string) => {
    const trimmed = q.trim()
    if (!trimmed) return
    router.push(`/app/chiedi?q=${encodeURIComponent(trimmed)}`)
  }

  const firstName = user?.name?.trim().split(/\s+/)[0]

  return (
    <div className="mx-auto max-w-3xl py-6 md:py-12">
      <h1 className="text-h1 md:text-display">{firstName ? t('titleNamed', { name: firstName }) : t('title')}</h1>
      <p className="mt-3 max-w-prose text-read text-ink-2">{t('lead')}</p>

      <form
        className="mt-8"
        onSubmit={(e) => {
          e.preventDefault()
          ask(question)
        }}
      >
        <label htmlFor="home-question" className="sr-only">
          {t('questionLabel')}
        </label>
        <div className="flex flex-col gap-2 rounded-lg border border-rule-2 bg-surface p-2 focus-within:border-union focus-within:ring-2 focus-within:ring-union/20 sm:flex-row sm:items-end">
          <textarea
            id="home-question"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                ask(question)
              }
            }}
            rows={2}
            placeholder={t('placeholder')}
            className="min-h-[56px] flex-1 resize-none bg-transparent px-2 py-1.5 text-read text-ink placeholder:text-ink-3 focus:outline-none"
          />
          <Button type="submit" disabled={!question.trim()} className="sm:mb-0.5">
            {t('send')}
          </Button>
        </div>
      </form>

      <ul className="mt-4 flex flex-wrap gap-2" aria-label={t('examples')}>
        {itemKeys(tc.raw('suggestions')).map((k) => {
          const s = tc(`suggestions.${k}`)
          return (
            <li key={k}>
              <button
                type="button"
                onClick={() => ask(s)}
                className="rounded-md border border-rule bg-surface px-3 py-1.5 text-left text-small text-ink-2 hover:border-rule-2 hover:text-ink"
              >
                {s}
              </button>
            </li>
          )
        })}
      </ul>

      <div className="mt-14 grid gap-px overflow-hidden rounded-lg border border-rule bg-rule sm:grid-cols-3">
        {TILES.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className="group flex flex-col gap-2 bg-surface p-5 no-underline transition-colors hover:bg-surface-2"
          >
            <item.icon className="h-5 w-5 text-union" aria-hidden="true" />
            <span className="text-h4 text-ink">{t(`tiles.${item.key}.title`)}</span>
            <span className="text-small text-ink-2">{t(`tiles.${item.key}.body`)}</span>
            <span className="mt-auto inline-flex items-center gap-1 pt-2 text-small font-medium text-union">
              {t('open')}
              <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden="true" />
            </span>
          </Link>
        ))}
      </div>
    </div>
  )
}
