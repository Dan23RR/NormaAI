'use client'

import Link from 'next/link'
import { Suspense, useEffect, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import {
  FileText,
  ArrowRight,
  CheckCircle2,
  AlertTriangle,
  Loader2,
} from 'lucide-react'

const API_URL =
  process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// Codex landing route (lead magnet).
//
// MKT-01: tutte le 22 email cold/follow-up Wave 2 linkano a
//   https://normaai-psi.vercel.app/codex?lead={lead_id}
// Prima di questa route quel link dava 404 e annullava il funnel.
// Qui leggiamo ?lead= per tracciare la provenienza del click (campo `referer`
// che il backend già persiste) e mostriamo il form di cattura lead che fa POST
// a /api/v1/leads e serve il download_url firmato restituito dal backend.

type FormStatus =
  | { kind: 'idle' }
  | { kind: 'submitting' }
  | { kind: 'success'; message: string; downloadUrl?: string }
  | { kind: 'error'; message: string }

export default function CodexPage() {
  useEffect(() => {
    document.body.classList.add('paper-bg')
    return () => document.body.classList.remove('paper-bg')
  }, [])

  return (
    <div className="min-h-screen bg-paper text-night">
      {/* ───────────────────────── NAV ───────────────────────── */}
      <nav className="sticky top-0 z-30 border-b border-line bg-paper/85 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <Link href="/" className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-night font-serif text-paper">
              N
            </div>
            <span className="text-lg font-semibold tracking-tight">NormaAI</span>
          </Link>
          <div className="flex items-center gap-3 text-sm">
            <Link href="/" className="hidden text-night-2 hover:text-night md:inline">
              Home
            </Link>
            <a
              href="mailto:info@normaai.org?subject=NormaAI%20demo%20call"
              className="rounded-md bg-clay px-4 py-2 font-medium text-white transition hover:bg-clay-deep"
            >
              Richiedi demo
            </a>
          </div>
        </div>
      </nav>

      {/* ─────────────────── CODEX (LEAD MAGNET) ─────────────────── */}
      <section className="border-b border-line bg-gradient-to-br from-paper-2 via-paper to-paper-2">
        <div className="mx-auto grid max-w-6xl gap-10 px-6 py-20 lg:grid-cols-12 lg:items-center">
          <div className="lg:col-span-7">
            <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-clay/50 bg-clay-soft px-3 py-1 text-xs text-clay">
              <FileText className="h-3.5 w-3.5" />
              Lead magnet · PDF · fonti UE/IT verificate · Italiano
            </div>
            <h1 className="text-3xl font-serif font-normal tracking-tight md:text-5xl">
              Codex Post-Omnibus 2025-2029
            </h1>
            <p className="mt-4 max-w-xl text-night-2">
              La guida operativa post-Omnibus I per chi gestisce CSRD/CSDDD/EU Taxonomy: scope,
              calendari, ESRS Set 1 ridotto. Mappe decisionali, calendario adempimenti, i 10 errori
              più comuni nelle prime disclosure CSRD. Testi UE + Gazzetta, zero PR aziendale.
            </p>
            <ul className="mt-6 space-y-2 text-sm text-night-2">
              <li className="flex items-start gap-2">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-clay" />
                Flowchart &quot;Sono in scope?&quot; per CSRD/CSDDD/EU Taxonomy
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-clay" />
                ESRS Set 1: cosa resta dopo il -61% dei datapoint
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-clay" />
                VSME Standard volontario: quando conviene adottarlo
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-clay" />
                Calendario 2026-2028 con deadline transposition + first reporting
              </li>
            </ul>
            <p className="mt-6 text-sm text-night-2">
              Vuoi vederlo applicato a un caso reale del tuo ufficio?{' '}
              <a
                href="mailto:info@normaai.org?subject=NormaAI%20demo%20call"
                className="text-clay underline-offset-4 hover:underline"
              >
                prenota una demo di 30 minuti →
              </a>
            </p>
          </div>
          <div className="lg:col-span-5">
            <Suspense fallback={<CodexFormFallback />}>
              <CodexForm />
            </Suspense>
          </div>
        </div>
      </section>

      {/* ─────────────────── FOOTER ─────────────────── */}
      <footer className="bg-paper-2">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-6 py-10 text-sm text-night-2 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded bg-night text-xs font-serif text-paper">
              N
            </div>
            <span>NormaAI © {new Date().getFullYear()}</span>
          </div>
          <div className="flex flex-wrap gap-5">
            <Link href="/privacy" className="hover:text-night">Privacy</Link>
            <Link href="/terms" className="hover:text-night">Termini</Link>
            <Link href="/security" className="hover:text-night">Sicurezza</Link>
            <a href="mailto:info@normaai.org" className="hover:text-night">Contatti</a>
          </div>
        </div>
      </footer>
    </div>
  )
}

// ───────────────────────── Sub-components ─────────────────────────

function CodexFormFallback() {
  return (
    <div className="rounded-xl border border-line bg-white p-6">
      <div className="flex items-center gap-2 text-sm text-night-2">
        <Loader2 className="h-4 w-4 animate-spin" />
        Caricamento...
      </div>
    </div>
  )
}

function CodexForm() {
  const searchParams = useSearchParams()
  // lead_id passato dalle email Wave 2 (?lead={lead_id}) - usato per tracciare
  // la provenienza del click e correlarlo al lead già censito nel CRM.
  const [leadRef, setLeadRef] = useState<string>('')
  const [status, setStatus] = useState<FormStatus>({ kind: 'idle' })

  useEffect(() => {
    const ref = searchParams.get('lead')
    if (ref) setLeadRef(ref.slice(0, 128))
  }, [searchParams])

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (status.kind === 'submitting') return

    const fd = new FormData(e.currentTarget)
    const payload = {
      email: String(fd.get('email') || '').trim(),
      org_name: String(fd.get('org') || '').trim() || undefined,
      role: String(fd.get('role') || '').trim() || undefined,
      source: 'codex_download',
    }

    if (!payload.email || !/.+@.+\..+/.test(payload.email)) {
      setStatus({ kind: 'error', message: 'Inserisci un indirizzo email valido.' })
      return
    }

    setStatus({ kind: 'submitting' })

    try {
      const res = await fetch(`${API_URL}/api/v1/leads`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        // Track del lead_id senza modifiche allo schema /api/v1/leads (campo
        // body assente): mandiamo l'URL completo della pagina (incl. ?lead=)
        // come Referer, che il backend già persiste nel campo `referer`.
        // Di default i browser strippano path+query su richieste cross-origin;
        // 'unsafe-url' forza l'invio dell'URL completo così il lead_id arriva.
        referrerPolicy: 'unsafe-url',
        body: JSON.stringify(payload),
      })

      if (res.status === 201 || res.status === 200) {
        const data = await res.json().catch(() => ({}))
        // Build absolute download URL: backend returns a relative path on /api/v1/...
        let downloadUrl: string | undefined = data?.download_url
        if (downloadUrl && downloadUrl.startsWith('/')) {
          downloadUrl = `${API_URL}${downloadUrl}`
        }
        setStatus({
          kind: 'success',
          message:
            data?.message ||
            'Richiesta registrata. Riceverai il Codex entro pochi secondi.',
          downloadUrl,
        })
        return
      }

      if (res.status === 429) {
        setStatus({
          kind: 'error',
          message:
            'Troppe richieste recenti dallo stesso indirizzo. Riprova tra un\'ora.',
        })
        return
      }

      if (res.status === 422) {
        setStatus({
          kind: 'error',
          message: 'Dati non validi. Controlla email e nome organizzazione.',
        })
        return
      }

      setStatus({
        kind: 'error',
        message: `Errore inatteso (${res.status}). Riprova o scrivi a info@normaai.org.`,
      })
    } catch (err) {
      setStatus({
        kind: 'error',
        message:
          'Impossibile contattare il server. Verifica la connessione e riprova.',
      })
    }
  }

  if (status.kind === 'success') {
    return (
      <div className="rounded-xl border border-emerald-600/30 bg-emerald-600/10 p-6">
        <div className="flex items-start gap-3">
          <div className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-emerald-600/10 text-emerald-700">
            <CheckCircle2 className="h-5 w-5" />
          </div>
          <div className="flex-1">
            <h2 className="text-lg font-semibold text-night">Richiesta ricevuta</h2>
            <p className="mt-1 text-sm text-night-2">{status.message}</p>
          </div>
        </div>

        {status.downloadUrl && (
          <a
            href={status.downloadUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-md bg-clay py-3 font-semibold text-white transition hover:bg-clay-deep"
          >
            <FileText className="h-4 w-4" />
            Scarica il Codex ora (PDF)
          </a>
        )}

        <p className="mt-4 text-xs text-night-2">
          Il link è personale e funziona per 30 giorni. Nel frattempo, vuoi parlarne 30 min?{' '}
          <a
            href="mailto:info@normaai.org?subject=NormaAI%20demo%20call"
            className="text-clay hover:text-clay-deep"
          >
            scrivimi
          </a>
          .
        </p>
      </div>
    )
  }

  return (
    <form
      className="rounded-xl border border-line bg-white p-6"
      onSubmit={handleSubmit}
      noValidate
    >
      <h2 className="text-lg font-semibold text-night">Scarica il Codex</h2>
      <p className="mt-1 text-sm text-night-2">
        Inserisci l&apos;email aziendale: il link di download compare subito qui sotto.
      </p>
      {/* lead_id dalla cold email Wave 2 (?lead=...): tenuto nel DOM per tracking/debug.
          Il valore viaggia al backend via Referer (referrerPolicy unsafe-url). */}
      {leadRef && <input type="hidden" name="lead_ref" value={leadRef} readOnly />}
      <label className="mt-5 block text-sm text-night-2">Email aziendale</label>
      <input
        name="email"
        type="email"
        required
        autoComplete="email"
        placeholder="nome@azienda.it"
        disabled={status.kind === 'submitting'}
        className="mt-2 w-full rounded-lg border border-line bg-paper px-3 py-2.5 text-night outline-none focus:border-clay disabled:opacity-60"
      />
      <label className="mt-4 block text-sm text-night-2">Nome organizzazione</label>
      <input
        name="org"
        autoComplete="organization"
        placeholder="Es: Acme S.p.A."
        disabled={status.kind === 'submitting'}
        className="mt-2 w-full rounded-lg border border-line bg-paper px-3 py-2.5 text-night outline-none focus:border-clay disabled:opacity-60"
      />
      <label className="mt-4 block text-sm text-night-2">Ruolo</label>
      <select
        name="role"
        defaultValue="Compliance Officer / DPO"
        disabled={status.kind === 'submitting'}
        className="mt-2 w-full rounded-lg border border-line bg-paper px-3 py-2.5 text-night outline-none focus:border-clay disabled:opacity-60"
      >
        <option>Compliance Officer / DPO</option>
        <option>CFO / Risk Manager</option>
        <option>Avvocato / Managing Partner studio</option>
        <option>Altro</option>
      </select>
      <button
        type="submit"
        disabled={status.kind === 'submitting'}
        className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-md bg-clay py-3 font-semibold text-white transition hover:bg-clay-deep disabled:cursor-wait disabled:opacity-70"
      >
        {status.kind === 'submitting' ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            Invio in corso...
          </>
        ) : (
          <>
            Scarica il Codex (PDF)
            <ArrowRight className="h-4 w-4" />
          </>
        )}
      </button>
      {status.kind === 'error' && (
        <div
          role="alert"
          className="mt-3 flex items-start gap-2 rounded-lg border border-red-700/30 bg-red-50 px-3 py-2 text-xs text-red-800"
        >
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>{status.message}</span>
        </div>
      )}
      <p className="mt-3 text-xs text-night-2">
        Niente newsletter automatiche. Solo il PDF + un follow-up manuale per capire se NormaAI può
        servirvi davvero.
      </p>
    </form>
  )
}
