'use client'

import Link from 'next/link'
import { Suspense, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useLocale, useTranslations } from 'next-intl'
import { useAuth } from '@/hooks/useAuth'
import { Logo } from '@/components/Logo'
import { Button } from '@/components/ui/Button'
import { Field, Input, describedBy } from '@/components/ui/Field'
import { LawQuote } from '@/components/ui/LawQuote'
import { eurlexLang } from '@/i18n/config'
import { useErrorText } from '@/i18n/errors'
import { AI_ACT_ART_50_1_IT } from '@/lib/law-passages'
import { eurlexUrl } from '@/lib/sources'

type Mode = 'login' | 'register'

function LoginForm() {
  const t = useTranslations('login')
  const errorText = useErrorText()
  const { login, register, loginDemo } = useAuth()
  const router = useRouter()
  const params = useSearchParams()
  const next = params.get('next') || '/app'
  const [mode, setMode] = useState<Mode>(params.get('invite') ? 'register' : 'login')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [orgName, setOrgName] = useState('')
  const [inviteCode, setInviteCode] = useState(params.get('invite') || '')

  const safeNext = next.startsWith('/') && !next.startsWith('//') ? next : '/app'

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      if (mode === 'register') {
        await register(email, password, name, orgName, inviteCode.trim() || undefined)
      } else {
        await login(email, password)
      }
      router.push(safeNext)
    } catch (err: unknown) {
      setError(errorText(err))
    } finally {
      setLoading(false)
    }
  }

  const handleDemo = () => {
    loginDemo()
    router.push('/app')
  }

  const switchTo = (next: Mode) => (chunks: React.ReactNode) => (
    <button
      type="button"
      className="text-union hover:underline"
      onClick={() => {
        setMode(next)
        setError('')
      }}
    >
      {chunks}
    </button>
  )

  return (
    <div className="w-full max-w-md">
      <h1 className="text-h2">{mode === 'register' ? t('titleRegister') : t('titleLogin')}</h1>
      <p className="mt-2 text-body text-ink-2">{mode === 'register' ? t('leadRegister') : t('leadLogin')}</p>

      {error && (
        <div className="mt-5 rounded-md border border-bad/30 bg-bad/5 px-3 py-2.5 text-small text-bad" role="alert">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="mt-6 space-y-4" noValidate>
        {mode === 'register' && (
          <>
            <Field label={t('invite')} htmlFor="invite" required>
              <Input
                id="invite"
                value={inviteCode}
                onChange={(e) => setInviteCode(e.target.value)}
                required
                autoComplete="off"
                spellCheck={false}
                placeholder={t('invitePlaceholder')}
              />
            </Field>
            <Field label={t('name')} htmlFor="name" required>
              <Input id="name" value={name} onChange={(e) => setName(e.target.value)} required autoComplete="name" />
            </Field>
            <Field label={t('org')} htmlFor="org" help={t('orgHelp')}>
              <Input
                id="org"
                value={orgName}
                onChange={(e) => setOrgName(e.target.value)}
                autoComplete="organization"
                aria-describedby={describedBy('org', { help: true })}
              />
            </Field>
          </>
        )}
        <Field label={t('email')} htmlFor="email" required>
          <Input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
            inputMode="email"
          />
        </Field>
        <Field label={t('password')} htmlFor="password" required help={mode === 'register' ? t('passwordHelp') : undefined}>
          <Input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
            autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
            aria-describedby={mode === 'register' ? describedBy('password', { help: true }) : undefined}
          />
        </Field>
        <Button type="submit" loading={loading} className="w-full" size="lg">
          {mode === 'register' ? t('submitRegister') : t('submitLogin')}
        </Button>
      </form>

      <p className="mt-4 text-small text-ink-2">
        {mode === 'register'
          ? t.rich('haveAccount', { login: switchTo('login') })
          : t.rich('haveInvite', {
              register: switchTo('register'),
              mail: (chunks) => (
                <a href="mailto:info@normaai.org?subject=Reimpostare%20la%20password" className="text-union hover:underline">
                  {chunks}
                </a>
              ),
            })}
      </p>

      <div className="mt-8 border-t border-rule pt-6">
        <Button variant="secondary" className="w-full" onClick={handleDemo}>
          {t('demo')}
        </Button>
        <p className="mt-2 text-caption text-ink-3">{t('demoNote')}</p>
      </div>

      <p className="mt-6 text-caption text-ink-3">
        {t.rich('terms', {
          terms: (chunks) => (
            <Link href="/terms" className="underline">
              {chunks}
            </Link>
          ),
          privacy: (chunks) => (
            <Link href="/privacy" className="underline">
              {chunks}
            </Link>
          ),
        })}
      </p>
    </div>
  )
}

export default function LoginPage() {
  const t = useTranslations('login')
  const tu = useTranslations('ui')
  const locale = useLocale()
  return (
    <div className="grid min-h-screen bg-surface lg:grid-cols-12">
      <aside className="hidden flex-col justify-between border-r border-rule bg-surface-2 p-10 lg:col-span-5 lg:flex">
        <Logo size="lg" />
        <div className="max-w-md">
          <p className="text-h3 text-ink">{t('claim')}</p>
          <LawQuote
            className="mt-6"
            quote={AI_ACT_ART_50_1_IT.quote}
            before={AI_ACT_ART_50_1_IT.before}
            lang={AI_ACT_ART_50_1_IT.lang}
            act={tu('acts.AI_ACT')}
            article={t('article')}
            celex={AI_ACT_ART_50_1_IT.celex}
            url={eurlexUrl(AI_ACT_ART_50_1_IT.celex, eurlexLang(locale))}
            origin="EUR-Lex"
          />
        </div>
        <p className="text-caption text-ink-3">{t('asideNote')}</p>
      </aside>
      <main className="flex items-center justify-center px-6 py-12 lg:col-span-7">
        <div className="w-full max-w-md">
          <div className="mb-8 lg:hidden">
            <Logo />
          </div>
          <Suspense fallback={null}>
            <LoginForm />
          </Suspense>
        </div>
      </main>
    </div>
  )
}
