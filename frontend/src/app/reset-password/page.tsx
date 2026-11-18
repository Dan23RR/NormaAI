'use client'

import Link from 'next/link'
import { Suspense, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { CheckCircle2, AlertTriangle, Mail } from 'lucide-react'
import { Logo } from '@/components/Logo'
import { Button, ButtonLink } from '@/components/ui/Button'
import { Field, Input, describedBy } from '@/components/ui/Field'
import { useErrorText } from '@/i18n/errors'
import { api, API_CONFIGURED } from '@/lib/api'
import { clearTokens } from '@/lib/auth'

const MIN_PASSWORD = 8

type State =
  | { kind: 'form' }
  | { kind: 'requested'; email: string }
  | { kind: 'done'; email: string }
  | { kind: 'failed'; message: string }

/**
 * /reset-password: without a token, ask for a link (POST /auth/password-reset,
 * the same answer whether or not the address has an account); with the token
 * of the link, choose the new password (POST /auth/password-reset/confirm).
 */
function ResetPassword({ token }: { token: string }) {
  const t = useTranslations('login.passwordReset')
  const errorText = useErrorText()
  const [state, setState] = useState<State>({ kind: 'form' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [repeat, setRepeat] = useState('')

  if (!API_CONFIGURED) {
    return (
      <div className="w-full max-w-md rounded-lg border border-rule bg-surface p-8" role="status">
        <h1 className="text-h3">{t('requestTitle')}</h1>
        <p className="mt-2 text-body text-ink-2">
          {t.rich('unavailableBody', {
            mail: (chunks) => (
              <a href="mailto:info@normaai.org" className="text-union underline hover:no-underline">
                {chunks}
              </a>
            ),
          })}
        </p>
        <ButtonLink href="/login" variant="secondary" className="mt-6 w-full">
          {t('backToLogin')}
        </ButtonLink>
      </div>
    )
  }

  const request = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await api.requestPasswordReset(email.trim())
      setState({ kind: 'requested', email: email.trim() })
    } catch (err) {
      setError(errorText(err))
    } finally {
      setLoading(false)
    }
  }

  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (password.length < MIN_PASSWORD) {
      setError(t('tooShort'))
      return
    }
    if (password !== repeat) {
      setError(t('mismatch'))
      return
    }
    setLoading(true)
    try {
      const res = await api.resetPassword(token, password)
      // Every session of the account has just ended, this browser's too.
      clearTokens()
      setState({ kind: 'done', email: res?.email ?? '' })
    } catch (err) {
      setState({ kind: 'failed', message: errorText(err, 'login.passwordReset.failedBody') })
    } finally {
      setLoading(false)
    }
  }

  if (state.kind !== 'form') {
    const ok = state.kind === 'done'
    const Icon = state.kind === 'requested' ? Mail : ok ? CheckCircle2 : AlertTriangle
    return (
      <div className="w-full max-w-md rounded-lg border border-rule bg-surface p-8" role="status" aria-live="polite">
        <div className="flex items-start gap-3">
          <Icon
            className={`mt-1 h-5 w-5 shrink-0 ${state.kind === 'failed' ? 'text-warn' : 'text-ok'}`}
            aria-hidden="true"
          />
          <div>
            <h1 className="text-h3">
              {state.kind === 'requested' ? t('requestedTitle') : ok ? t('doneTitle') : t('failedTitle')}
            </h1>
            <p className="mt-2 text-body text-ink-2">
              {state.kind === 'requested'
                ? t('requestedBody', { email: state.email })
                : state.kind === 'done'
                  ? t('doneBody', { email: state.email })
                  : state.message}
            </p>
          </div>
        </div>
        <div className="mt-6">
          {state.kind === 'failed' ? (
            <ButtonLink href="/reset-password" className="w-full">
              {t('requestAgain')}
            </ButtonLink>
          ) : (
            <ButtonLink href="/login" className="w-full" variant={ok ? 'primary' : 'secondary'}>
              {ok ? t('goToLogin') : t('backToLogin')}
            </ButtonLink>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="w-full max-w-md rounded-lg border border-rule bg-surface p-8">
      <h1 className="text-h3">{token ? t('setTitle') : t('requestTitle')}</h1>
      <p className="mt-2 text-body text-ink-2">{token ? t('setLead') : t('requestLead')}</p>

      {error && (
        <div className="mt-5 rounded-md border border-bad/30 bg-bad/5 px-3 py-2.5 text-small text-bad" role="alert">
          {error}
        </div>
      )}

      {token ? (
        <form onSubmit={save} className="mt-6 space-y-4" noValidate>
          <Field label={t('newPassword')} htmlFor="new-password" required help={t('passwordHelp')}>
            <Input
              id="new-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={MIN_PASSWORD}
              autoComplete="new-password"
              aria-describedby={describedBy('new-password', { help: true })}
            />
          </Field>
          <Field label={t('confirmPassword')} htmlFor="repeat-password" required>
            <Input
              id="repeat-password"
              type="password"
              value={repeat}
              onChange={(e) => setRepeat(e.target.value)}
              required
              minLength={MIN_PASSWORD}
              autoComplete="new-password"
            />
          </Field>
          <Button type="submit" loading={loading} className="w-full" size="lg">
            {t('submitSet')}
          </Button>
        </form>
      ) : (
        <form onSubmit={request} className="mt-6 space-y-4" noValidate>
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
          <Button type="submit" loading={loading} className="w-full" size="lg">
            {t('submitRequest')}
          </Button>
        </form>
      )}

      <p className="mt-4 text-small text-ink-2">
        <Link href="/login" className="text-union underline hover:no-underline">
          {t('backToLogin')}
        </Link>
      </p>
    </div>
  )
}

/** A new token (or none, after "ask for a new link") starts the page over. */
function ResetPasswordRoute() {
  const token = useSearchParams().get('token') || ''
  return <ResetPassword key={token} token={token} />
}

export default function ResetPasswordPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-8 bg-canvas px-6 py-12">
      <Logo />
      <Suspense fallback={null}>
        <ResetPasswordRoute />
      </Suspense>
    </main>
  )
}
