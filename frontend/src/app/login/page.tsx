'use client'

import Link from 'next/link'
import { Suspense, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useAuth } from '@/hooks/useAuth'
import { Logo } from '@/components/Logo'
import { Button } from '@/components/ui/Button'
import { Field, Input, describedBy } from '@/components/ui/Field'
import { LawQuote } from '@/components/ui/LawQuote'
import { eurlexUrl } from '@/lib/sources'

type Mode = 'login' | 'register'

function LoginForm() {
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
      setError(err instanceof Error ? err.message : 'Qualcosa non ha funzionato. Riprova.')
    } finally {
      setLoading(false)
    }
  }

  const handleDemo = () => {
    loginDemo()
    router.push('/app')
  }

  return (
    <div className="w-full max-w-md">
      <h1 className="text-h2">{mode === 'register' ? 'Crea il tuo account' : 'Accedi a NormaAI'}</h1>
      <p className="mt-2 text-body text-ink-2">
        {mode === 'register'
          ? 'Serve un codice di invito. Se non lo hai, richiedi una demo dalla pagina principale.'
          : 'Usa l’email e la password del tuo account.'}
      </p>

      {error && (
        <div className="mt-5 rounded-md border border-bad/30 bg-bad/5 px-3 py-2.5 text-small text-bad" role="alert">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="mt-6 space-y-4" noValidate>
        {mode === 'register' && (
          <>
            <Field label="Codice di invito" htmlFor="invite" required>
              <Input
                id="invite"
                value={inviteCode}
                onChange={(e) => setInviteCode(e.target.value)}
                required
                autoComplete="off"
                spellCheck={false}
                placeholder="Il codice ricevuto via email"
              />
            </Field>
            <Field label="Nome e cognome" htmlFor="name" required>
              <Input id="name" value={name} onChange={(e) => setName(e.target.value)} required autoComplete="name" />
            </Field>
            <Field
              label="Organizzazione"
              htmlFor="org"
              help="Lascia vuoto se l'invito ti aggiunge a un'organizzazione esistente."
            >
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
        <Field label="Email" htmlFor="email" required>
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
        <Field
          label="Password"
          htmlFor="password"
          required
          help={mode === 'register' ? 'Almeno 8 caratteri.' : undefined}
        >
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
          {mode === 'register' ? 'Crea l’account' : 'Accedi'}
        </Button>
      </form>

      <p className="mt-4 text-small text-ink-2">
        {mode === 'register' ? (
          <>
            Hai già un account?{' '}
            <button type="button" className="text-union hover:underline" onClick={() => { setMode('login'); setError('') }}>
              Accedi
            </button>
          </>
        ) : (
          <>
            Hai un codice di invito?{' '}
            <button type="button" className="text-union hover:underline" onClick={() => { setMode('register'); setError('') }}>
              Crea l’account
            </button>
            . Password dimenticata? Scrivi a{' '}
            <a href="mailto:info@normaai.org?subject=Reimpostare%20la%20password" className="text-union hover:underline">
              info@normaai.org
            </a>
            .
          </>
        )}
      </p>

      <div className="mt-8 border-t border-rule pt-6">
        <Button variant="secondary" className="w-full" onClick={handleDemo}>
          Apri la demo con dati di esempio
        </Button>
        <p className="mt-2 text-caption text-ink-3">
          Nessun account necessario. Risposte, clienti e analisi sono esempi, non il corpus reale.
        </p>
      </div>

      <p className="mt-6 text-caption text-ink-3">
        Accedendo accetti i{' '}
        <Link href="/terms" className="underline">
          Termini di servizio
        </Link>{' '}
        e la{' '}
        <Link href="/privacy" className="underline">
          Privacy
        </Link>
        .
      </p>
    </div>
  )
}

export default function LoginPage() {
  return (
    <div className="grid min-h-screen bg-surface lg:grid-cols-12">
      <aside className="hidden flex-col justify-between border-r border-rule bg-surface-2 p-10 lg:col-span-5 lg:flex">
        <Logo size="lg" />
        <div className="max-w-md">
          <p className="text-h3 text-ink">
            Ogni risposta mostra il passaggio di legge che la sostiene.
          </p>
          <LawQuote
            className="mt-6"
            quote="siano informate del fatto che stanno interagendo con un sistema di IA"
            before="I fornitori garantiscono che i sistemi di IA destinati a interagire direttamente con le persone fisiche sono progettati e sviluppati in modo tale che le persone fisiche interessate"
            act="Regolamento (UE) 2024/1689"
            article="art. 50, par. 1"
            celex="32024R1689"
            url={eurlexUrl('32024R1689')}
            origin="EUR-Lex"
          />
        </div>
        <p className="text-caption text-ink-3">Codice aperto su GitHub. Dati in Europa.</p>
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
