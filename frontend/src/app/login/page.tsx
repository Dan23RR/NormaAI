'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/hooks/useAuth'
import { Play, KeyRound } from 'lucide-react'

export default function LoginPage() {
  const { login, register, loginDemo } = useAuth()
  const router = useRouter()
  const [isRegister, setIsRegister] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [orgName, setOrgName] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      if (isRegister) {
        await register(email, password, name, orgName)
      } else {
        await login(email, password)
      }
      router.push('/dashboard')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  const handleDemoLogin = () => {
    loginDemo()
    router.push('/dashboard')
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-accent to-accent2 flex items-center justify-center text-white font-extrabold text-lg">
              N
            </div>
            <span className="text-2xl font-bold tracking-tight">
              NormaAI <span className="font-light text-slate-400">Intelligence</span>
            </span>
          </div>
          <p className="text-sm text-slate-500">EU Regulatory Compliance Platform</p>
        </div>

        {/* Card */}
        <div className="bg-surface border border-white/[0.08] rounded-xl p-8">
          <h2 className="text-lg font-semibold mb-6">
            {isRegister ? 'Create account' : 'Sign in'}
          </h2>

          {error && (
            <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm" role="alert">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {isRegister && (
              <>
                <div>
                  <label htmlFor="login-name" className="block text-sm text-slate-400 mb-1.5">Full name</label>
                  <input
                    id="login-name"
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    required
                    autoComplete="name"
                    className="w-full px-3 py-2.5 bg-surface2 border border-white/[0.08] rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-accent/50 transition"
                    placeholder="Mario Rossi"
                  />
                </div>
                <div>
                  <label htmlFor="login-org" className="block text-sm text-slate-400 mb-1.5">Organization</label>
                  <input
                    id="login-org"
                    type="text"
                    value={orgName}
                    onChange={(e) => setOrgName(e.target.value)}
                    required
                    autoComplete="organization"
                    className="w-full px-3 py-2.5 bg-surface2 border border-white/[0.08] rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-accent/50 transition"
                    placeholder="Acme Srl"
                  />
                </div>
              </>
            )}

            <div>
              <label htmlFor="login-email" className="block text-sm text-slate-400 mb-1.5">Email</label>
              <input
                id="login-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
                className="w-full px-3 py-2.5 bg-surface2 border border-white/[0.08] rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-accent/50 transition"
                placeholder="you@company.com"
              />
            </div>

            <div>
              <label htmlFor="login-password" className="block text-sm text-slate-400 mb-1.5">Password</label>
              <input
                id="login-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                autoComplete={isRegister ? 'new-password' : 'current-password'}
                className="w-full px-3 py-2.5 bg-surface2 border border-white/[0.08] rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-accent/50 transition"
                placeholder="Min. 8 characters"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 rounded-lg bg-gradient-to-r from-accent to-accent2 text-white font-medium hover:opacity-90 transition disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {loading && <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />}
              {isRegister ? 'Create account' : 'Sign in'}
            </button>
          </form>

          {/* Divider */}
          <div className="flex items-center gap-3 my-6">
            <div className="flex-1 h-px bg-white/[0.06]" />
            <span className="text-xs text-slate-600">oppure</span>
            <div className="flex-1 h-px bg-white/[0.06]" />
          </div>

          {/* Demo button */}
          <button
            onClick={handleDemoLogin}
            className="w-full py-2.5 rounded-lg border border-green-500/30 bg-green-500/5 text-green-400 font-medium hover:bg-green-500/10 transition flex items-center justify-center gap-2"
          >
            <Play size={16} />
            Entra in modalità Demo
          </button>
          <p className="text-[11px] text-slate-600 text-center mt-2">
            Esplora la dashboard con dati di esempio, senza bisogno del backend
          </p>

          {/* SSO */}
          <div className="flex items-center gap-3 my-5">
            <div className="flex-1 h-px bg-white/[0.06]" />
            <span className="text-xs text-slate-600">SSO Enterprise</span>
            <div className="flex-1 h-px bg-white/[0.06]" />
          </div>

          <button
            onClick={() => alert('SSO integration requires backend configuration. Contact admin to set up SAML/OIDC provider.')}
            className="w-full py-2.5 rounded-lg border border-white/[0.08] bg-white/[0.02] text-slate-300 font-medium hover:bg-white/[0.05] transition flex items-center justify-center gap-2"
          >
            <KeyRound size={16} />
            Sign in with SSO
          </button>
          <div className="flex justify-center gap-4 mt-2">
            {['Okta', 'Azure AD', 'Google'].map(provider => (
              <span key={provider} className="text-[10px] text-slate-600">{provider}</span>
            ))}
          </div>

          <p className="text-[10px] text-slate-600 text-center mt-4">
            Accedendo accetti i{' '}
            <a href="/terms" className="text-accent hover:underline">Termini di Servizio</a>
            {' '}e la{' '}
            <a href="/privacy" className="text-accent hover:underline">Privacy Policy</a>.
          </p>

          <div className="mt-5 text-center text-sm text-slate-500">
            {isRegister ? 'Already have an account?' : "Don't have an account?"}{' '}
            <button
              onClick={() => { setIsRegister(!isRegister); setError('') }}
              className="text-accent hover:underline"
            >
              {isRegister ? 'Sign in' : 'Create one'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
