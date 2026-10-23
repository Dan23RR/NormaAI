'use client'

import { Suspense, useEffect, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { CheckCircle2, AlertTriangle } from 'lucide-react'
import { Logo } from '@/components/Logo'
import { ButtonLink, Spinner } from '@/components/ui/Button'
import { useErrorText } from '@/i18n/errors'
import { api } from '@/lib/api'

type State =
  | { kind: 'missing' }
  | { kind: 'verifying' }
  | { kind: 'verified'; email: string }
  | { kind: 'already'; email: string }
  | { kind: 'failed'; message: string }

interface VerifyResponse {
  status: 'verified' | 'already_verified'
  email: string
}

/** Landing of the link in the verification email: /verify-email?token=... */
function VerifyEmail() {
  const t = useTranslations('login.verifyEmail')
  const errorText = useErrorText()
  const params = useSearchParams()
  const token = params.get('token') || ''
  const [state, setState] = useState<State>(() => (token ? { kind: 'verifying' } : { kind: 'missing' }))

  useEffect(() => {
    if (!token) return
    let alive = true
    api
      .post<VerifyResponse>('/api/v1/auth/verify-email', { token })
      .then((res) => {
        if (!alive) return
        setState(
          res?.status === 'already_verified'
            ? { kind: 'already', email: res.email }
            : { kind: 'verified', email: res?.email ?? '' },
        )
      })
      .catch((err) => {
        if (alive) setState({ kind: 'failed', message: errorText(err, 'login.verifyEmail.failedBody') })
      })
    return () => {
      alive = false
    }
  }, [token, errorText])

  const ok = state.kind === 'verified' || state.kind === 'already'

  return (
    <div className="w-full max-w-md rounded-lg border border-rule bg-surface p-8" role="status" aria-live="polite">
      {state.kind === 'verifying' ? (
        <div className="flex items-center gap-3">
          <Spinner className="h-5 w-5 text-union" />
          <p className="text-body text-ink-2">{t('verifying')}</p>
        </div>
      ) : (
        <>
          <div className="flex items-start gap-3">
            {ok ? (
              <CheckCircle2 className="mt-1 h-5 w-5 shrink-0 text-ok" aria-hidden="true" />
            ) : (
              <AlertTriangle className="mt-1 h-5 w-5 shrink-0 text-warn" aria-hidden="true" />
            )}
            <div>
              <h1 className="text-h3">
                {state.kind === 'verified'
                  ? t('verifiedTitle')
                  : state.kind === 'already'
                    ? t('alreadyTitle')
                    : state.kind === 'missing'
                      ? t('missingTitle')
                      : t('failedTitle')}
              </h1>
              <p className="mt-2 text-body text-ink-2">
                {state.kind === 'verified'
                  ? t('verifiedBody', { email: state.email })
                  : state.kind === 'already'
                    ? t('alreadyBody', { email: state.email })
                    : state.kind === 'missing'
                      ? t('missingBody')
                      : state.message}
              </p>
            </div>
          </div>
          <div className="mt-6">
            <ButtonLink href={ok ? '/app' : '/login'} className="w-full">
              {ok ? t('goToApp') : t('goToLogin')}
            </ButtonLink>
          </div>
        </>
      )}
    </div>
  )
}

export default function VerifyEmailPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-8 bg-canvas px-6 py-12">
      <Logo />
      <Suspense fallback={null}>
        <VerifyEmail />
      </Suspense>
    </main>
  )
}
