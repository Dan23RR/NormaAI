'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import {
  ShieldCheck,
  Database,
  GitBranch,
  CircuitBoard,
  Globe2,
  FileText,
  Zap,
  ArrowRight,
  CheckCircle2,
  AlertTriangle,
  Loader2,
} from 'lucide-react'
import { getAccessToken } from '@/lib/auth'

// Lead submission target:
// - NEXT_PUBLIC_API_URL set  -> FastAPI backend /api/v1/leads (full pipeline)
// - unset (today's prod)     -> same-origin serverless /api/leads
//   (NEVER default to localhost: in prod that posts to the visitor's own
//   machine and silently kills the funnel.)
const API_URL = process.env.NEXT_PUBLIC_API_URL || ''
const LEADS_ENDPOINT = API_URL ? `${API_URL}/api/v1/leads` : '/api/leads'

// Public landing page (Italian, ICP Wave 2: H1 compliance officer mid-market / H2 studi legali generalisti / H3 CFO banche-assicurazioni piccole).
// Warm-paper editorial theme (public pages only — dashboard stays dark).
// Auth-aware: shows "Vai alla dashboard" if user has a valid token.

type FormStatus =
  | { kind: 'idle' }
  | { kind: 'submitting' }
  | { kind: 'success'; message: string; downloadUrl?: string }
  | { kind: 'error'; message: string }

export default function Home() {
  const [authed, setAuthed] = useState<boolean>(false)

  useEffect(() => {
    setAuthed(Boolean(getAccessToken()))
    // Opt this page into the warm-paper theme (scrollbar/selection/bg).
    document.body.classList.add('paper-bg')
    return () => document.body.classList.remove('paper-bg')
  }, [])

  return (
    <div className="min-h-screen bg-paper text-night">
      {/* ───────────────────────── NAV ───────────────────────── */}
      <nav className="sticky top-0 z-30 border-b border-line bg-paper/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-night font-serif text-lg text-paper">
              N
            </div>
            <span className="font-serif text-xl tracking-tight">NormaAI</span>
          </Link>
          <div className="flex items-center gap-5 text-sm">
            <a href="#capabilities" className="hidden text-night-2 transition hover:text-night md:inline">
              Cosa fa
            </a>
            <a href="#framework" className="hidden text-night-2 transition hover:text-night md:inline">
              Framework
            </a>
            <a href="#proof" className="hidden text-night-2 transition hover:text-night md:inline">
              Tecnologia
            </a>
            <Link href="/metodo" className="hidden text-night-2 transition hover:text-night md:inline">
              Metodo
            </Link>
            <a href="#contact" className="hidden text-night-2 transition hover:text-night md:inline">
              Contatti
            </a>
            {authed ? (
              <Link
                href="/dashboard"
                className="rounded-md bg-night px-4 py-2 font-medium text-paper transition hover:bg-coal-2"
              >
                Vai alla dashboard
              </Link>
            ) : (
              <>
                <Link href="/login" className="text-night-2 transition hover:text-night">
                  Accedi
                </Link>
                <a
                  href="#contact"
                  className="rounded-md bg-night px-4 py-2 font-medium text-paper transition hover:bg-coal-2"
                >
                  Richiedi demo
                </a>
              </>
            )}
          </div>
        </div>
      </nav>

      {/* ─────────────────────── HERO ─────────────────────── */}
      <section className="mx-auto max-w-6xl px-6 pb-24 pt-16 md:pt-24">
        <div className="grid gap-12 lg:grid-cols-12 lg:items-center">
          <div className="lg:col-span-7">
            <p className="mb-6 text-xs font-medium uppercase tracking-[0.18em] text-night-2">
              Aggiornato post-Omnibus I · CSRD scope 1.000+ dipendenti
            </p>
            <h1 className="font-serif text-5xl font-normal leading-[1.08] tracking-tight md:text-[64px]">
              Compliance EU senza{' '}
              <em className="italic text-clay">allucinazioni</em> AI.
            </h1>
            <p className="mt-7 max-w-xl text-lg leading-relaxed text-night-2">
              Il copilota normativo difendibile in audit per chi gestisce 7 framework EU. Citazioni
              primary source da EUR-Lex SPARQL, verificate con Chain-of-Verification, integrazione
              Normattiva per il diritto italiano.
            </p>
            <div className="mt-9 flex flex-wrap gap-3">
              <a
                href="#codex"
                className="inline-flex items-center gap-2 rounded-md bg-clay px-5 py-3 font-medium text-white transition hover:bg-clay-deep"
              >
                <FileText className="h-4 w-4" />
                Scarica il Codex Post-Omnibus (PDF)
                <ArrowRight className="h-4 w-4" />
              </a>
            </div>
            <p className="mt-4 text-sm text-night-2">
              Oppure{' '}
              <a href="#contact" className="font-medium text-night underline decoration-clay decoration-2 underline-offset-4 transition hover:text-clay">
                prenota una demo di 30 minuti →
              </a>
            </p>
            <p className="mt-3 text-xs text-night-3">
              Pilot dedicato a partire da € 2.500 + IVA · Setup in 7 giorni · Nessun lock-in
            </p>
          </div>

          {/* Hero card right — the product, dark on paper */}
          <div className="lg:col-span-5">
            <div className="rounded-xl bg-coal p-6 text-[#E8E6E0] shadow-[0_24px_60px_-12px_rgba(20,20,19,0.35)]">
              <div className="mb-4 flex items-center justify-between text-xs text-[#9C9A92]">
                <span>Esempio risposta · CSRD post-Omnibus</span>
                <span className="rounded-full bg-emerald-400/10 px-2 py-0.5 text-emerald-300">
                  confidence 0.94
                </span>
              </div>
              <p className="text-sm leading-relaxed">
                Una società con 800 dipendenti e ricavi €50M{' '}
                <strong className="text-white">non rientra</strong> nel perimetro CSRD dopo
                l'Omnibus I, che ha innalzato la soglia a{' '}
                <strong className="text-white">1.000+ dipendenti e €450M di ricavi</strong> (criterio cumulativo).
              </p>
              <div className="mt-4 space-y-2 border-t border-white/10 pt-4 text-xs text-[#9C9A92]">
                <div className="flex items-start gap-2">
                  <FileText className="mt-0.5 h-3.5 w-3.5 shrink-0 text-clay" />
                  <span>
                    <strong className="text-[#E8E6E0]">Direttiva (UE) 2022/2464</strong>, Art. 19a — come
                    modificata dalla Direttiva (UE) 2026/470 (Omnibus I)
                  </span>
                </div>
                <div className="flex items-start gap-2">
                  <FileText className="mt-0.5 h-3.5 w-3.5 shrink-0 text-clay" />
                  <span>
                    <strong className="text-[#E8E6E0]">D.Lgs. 125/2024</strong>, Art. 4 — recepimento
                    italiano
                  </span>
                </div>
                <div className="flex items-start gap-2 pt-2 text-emerald-300">
                  <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  <span>3/3 citazioni verificate · 0 fonti inventate</span>
                </div>
              </div>
            </div>
            <p className="mt-3 text-center text-xs text-night-3">
              Output reale dell'agente Q&A, citazioni gated da pipeline CoVe
            </p>
          </div>
        </div>
      </section>

      {/* ─────────────────── PER CHI (ICP H1/H2/H3) ─────────────────── */}
      <section className="border-t border-line bg-paper-2">
        <div className="mx-auto max-w-6xl px-6 py-20">
          <div className="mb-12 max-w-3xl">
            <p className="mb-4 text-xs font-medium uppercase tracking-[0.18em] text-night-2">Per chi</p>
            <h2 className="font-serif text-3xl font-normal tracking-tight md:text-[40px] md:leading-[1.15]">
              Per chi gestisce compliance UE e non si può permettere allucinazioni.
            </h2>
            <p className="mt-5 leading-relaxed text-night-2">
              Tre profili. Tre pitch diversi. Una piattaforma sotto il cofano: Q&A su 7 framework UE
              con citazione primary source EUR-Lex in 30 secondi, pipeline anti-hallucination 5 fasi,
              312/312 test citazioni passing.
            </p>
          </div>
          <div className="grid gap-5 md:grid-cols-3">
            <ICPCardV2
              tag="Compliance officer interno"
              tagColor="#C2613F"
              audience="Mid-market 250–1.000 dip."
              pain="1 persona, 7 framework UE. Il CFO chiede 'siamo a posto con X?' e tu devi rispondere con citazione articolo, non opinione."
              solution="Copilota normativo da staff-augmentation. Q&A con citazione EUR-Lex in 30 secondi. CSRD post-Omnibus, AI Act, DORA, NIS2, GDPR, EU Taxonomy, CSDDD."
              cta="Codex Post-Omnibus →"
              ctaHref="#codex"
            />
            <ICPCardV2
              tag="Studi legali generalisti"
              tagColor="#6B5CA5"
              audience="3–15 avvocati, no specializzazione ESG"
              pain="Vorresti offrire compliance UE ai clienti aziendali ma assumere un partner senior costa €150k+ e il volume non è certo."
              solution="Capacity-multiplier: voi mantenete relazione/firma, NormaAI vi dà la base normativa verificata. Pricing add-on per cliente del cliente."
              cta="Pilot €2.500 — 3 mesi unlimited →"
              ctaHref="#contact"
            />
            <ICPCardV2
              tag="CFO / Risk Manager"
              tagColor="#2E7D6B"
              audience="Banche, SIM, SGR, mutue piccole sotto DORA"
              pain="DORA ti obbliga a ICT risk + third party + incident + TLPT. 5 atti delegati 2024 + circolari Banca d'Italia/IVASS. Audit Bd'I-ready richiesto."
              solution="Framework DORA completo mappato: Reg. 2024/1773-2957 + circolari. Risposta con citazione in 30s. Codex DORA estratto 6 pag. companion."
              cta="Codex DORA + framework →"
              ctaHref="#codex"
            />
          </div>
        </div>
      </section>

      {/* ─────────────────── 7 FRAMEWORK ─────────────────── */}
      <section id="framework" className="border-t border-line">
        <div className="mx-auto max-w-6xl px-6 py-20">
          <p className="mb-4 text-xs font-medium uppercase tracking-[0.18em] text-night-2">Copertura normativa</p>
          <h2 className="font-serif text-3xl font-normal tracking-tight md:text-[40px]">
            7 framework. Aggiornati ogni notte da EUR-Lex.
          </h2>
          <p className="mt-4 max-w-2xl leading-relaxed text-night-2">
            La crawler SPARQL ufficiale ingerisce direttive, regolamenti e implementing acts non
            appena pubblicati nella Gazzetta Ufficiale UE. Il diritto italiano arriva da
            Normattiva via Open Data API.
          </p>
          <div className="mt-10 grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            <FwCard tag="CSRD" name="Corporate Sustainability Reporting" note="Post-Omnibus" />
            <FwCard tag="CSDDD" name="Due Diligence Direttiva" note="Recepimento 26 luglio 2028" />
            <FwCard tag="AI Act" name="Regolamento UE AI" note="Sistemi alto rischio" />
            <FwCard tag="DORA" name="Digital Operational Resilience" note="Settore finanziario" />
            <FwCard tag="NIS2" name="Cybersecurity dir." note="Soggetti essenziali/important" />
            <FwCard tag="EU Taxonomy" name="Finanza sostenibile" note="6 obiettivi ambientali" />
            <FwCard tag="GDPR" name="Data Protection" note="con guidance EDPB" />
            <FwCard tag="ESRS" name="Set 1 ridotto -61%" note="VSME volontario" />
            <FwCard tag="CRA" name="Cyber Resilience Act" note="Novità · reporting dall'11 set 2026" highlight />
          </div>
        </div>
      </section>

      {/* ─────────────────── COME FUNZIONA ─────────────────── */}
      <section id="capabilities" className="border-t border-line bg-paper-2">
        <div className="mx-auto max-w-6xl px-6 py-20">
          <p className="mb-4 text-xs font-medium uppercase tracking-[0.18em] text-night-2">Come funziona</p>
          <h2 className="font-serif text-3xl font-normal tracking-tight md:text-[40px]">
            Tre casi d'uso. Una piattaforma.
          </h2>
          <div className="mt-10 grid gap-5 md:grid-cols-3">
            <UseCase
              n="01"
              title="Q&A regolatorio con citazioni"
              body="Una domanda in linguaggio naturale, una risposta gated da CoVe (Chain-of-Verification). Cita articolo, comma, e quote testuale. Streaming SSE in tempo reale."
              points={['Inglese + Italiano', 'Profilo aziendale opzionale', '< 8s end-to-end']}
            />
            <UseCase
              n="02"
              title="Gap analysis per cliente"
              body="Carichi un policy document, scegli il framework, ottieni un report di compliance per requisito con scoring 0–100 e remediation plan ordinato per impatto."
              points={['Per-requirement scoring', 'PDF executive summary', 'Multi-framework cross-check']}
            />
            <UseCase
              n="03"
              title="Impact monitor su novità normative"
              body="Inserisci un emendamento o una proposta legislativa, ottieni l'impatto stimato sul perimetro del cliente: obblighi nuovi, disclosure aggiuntive, deadline."
              points={['Alert proattivi su nuove pubblicazioni', 'Diff testuale tra versioni', 'Storico assessment']}
            />
          </div>
        </div>
      </section>

      {/* ─────────────────── PROOF / TECH ─────────────────── */}
      <section id="proof" className="border-t border-line">
        <div className="mx-auto max-w-6xl px-6 py-20">
          <p className="mb-4 text-xs font-medium uppercase tracking-[0.18em] text-night-2">Tecnologia</p>
          <h2 className="font-serif text-3xl font-normal tracking-tight md:text-[40px]">
            Architettura progettata per essere difendibile in audit.
          </h2>
          <p className="mt-4 max-w-2xl leading-relaxed text-night-2">
            La differenza tra un wrapper di ChatGPT e un copilota da rivendere a un cliente
            regulated è verificabile, riga per riga.
          </p>
          <div className="mt-10 grid gap-4 md:grid-cols-2">
            <ProofRow
              icon={<Database className="h-5 w-5" />}
              title="Hybrid retrieval BGE-base + BM25 + RRF"
              body="Recupero semantico denso (768d) e lessicale sparse, fusione Reciprocal Rank Fusion. Multi-tenant via Qdrant filter su org_id."
            />
            <ProofRow
              icon={<ShieldCheck className="h-5 w-5" />}
              title="Pipeline CoVe a 5 fasi"
              body="Plan → Extract claims → Verify each → Revise draft → Output. Anti-allucinazione strutturale, non un guardrail post-hoc."
            />
            <ProofRow
              icon={<Globe2 className="h-5 w-5" />}
              title="EUR-Lex SPARQL ingestion notturna"
              body="Endpoint ufficiale publications.europa.eu. Filtro temporale: chunk superseded sono esclusi di default per correttezza giuridica."
            />
            <ProofRow
              icon={<GitBranch className="h-5 w-5" />}
              title="Multi-tenant con Row-Level Security"
              body="PostgreSQL RLS per isolamento dati cliente. JWT RS256 con organization scope. Brute-force protection Redis-backed."
            />
            <ProofRow
              icon={<CircuitBoard className="h-5 w-5" />}
              title="312/312 test passati al G1 verificato"
              body="Test suite real-run: 38 unit, 57 DB/auth, 30 cache, 13 retrieval, 60 agent, 30 integration esterne, 36 API integration, 48 monte-carlo. 99% pass-rate empirico."
            />
            <ProofRow
              icon={<Zap className="h-5 w-5" />}
              title="LLM provider intercambiabile"
              body="Gemini 2.5 Flash di default, fallback Claude Sonnet 4.5. Possibile self-host con Ollama per regime DPIA-strict."
            />
          </div>
        </div>
      </section>

      {/* ─────────────────── CODEX (LEAD MAGNET) ─────────────────── */}
      <section id="codex" className="border-t border-line bg-paper-2">
        <div className="mx-auto grid max-w-6xl gap-12 px-6 py-20 lg:grid-cols-12 lg:items-center">
          <div className="lg:col-span-7">
            <p className="mb-4 inline-flex items-center gap-2 text-xs font-medium uppercase tracking-[0.18em] text-clay">
              <FileText className="h-3.5 w-3.5" />
              Guida gratuita · PDF · fonti UE/IT verificate
            </p>
            <h2 className="font-serif text-3xl font-normal tracking-tight md:text-[40px]">
              Codex Post-Omnibus 2025–2029
            </h2>
            <p className="mt-4 leading-relaxed text-night-2">
              La guida operativa post-Omnibus I per chi gestisce CSRD/CSDDD/EU Taxonomy: scope,
              calendari, ESRS Set 1 ridotto. Mappe decisionali, calendario adempimenti,
              i 10 errori più comuni nelle prime disclosure CSRD.
            </p>
            <ul className="mt-6 space-y-2.5 text-sm text-night-2">
              <li className="flex items-start gap-2.5">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-clay" />
                Flowchart "Sono in scope?" per CSRD/CSDDD/EU Taxonomy
              </li>
              <li className="flex items-start gap-2.5">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-clay" />
                ESRS Set 1: cosa resta dopo il -61% dei datapoint
              </li>
              <li className="flex items-start gap-2.5">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-clay" />
                VSME Standard volontario: quando conviene adottarlo
              </li>
              <li className="flex items-start gap-2.5">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-clay" />
                Calendario 2026–2029 con deadline transposition + first reporting
              </li>
            </ul>
          </div>
          <div className="lg:col-span-5">
            <CodexForm />
          </div>
        </div>
      </section>

      {/* ─────────────────── CONTACT / DEMO — dark closing block ─────────────────── */}
      <section id="contact" className="bg-coal text-[#E8E6E0]">
        <div className="mx-auto max-w-3xl px-6 py-24 text-center">
          <p className="mb-5 text-xs font-medium uppercase tracking-[0.18em] text-[#9C9A92]">Demo</p>
          <h2 className="font-serif text-3xl font-normal tracking-tight text-white md:text-[40px]">
            30 minuti, una domanda vera dal tuo lavoro reale.
          </h2>
          <p className="mx-auto mt-5 max-w-xl leading-relaxed text-[#B5B3AA]">
            Mostriamo NormaAI su un caso reale che ci porti tu. Se la risposta non è meglio della
            tua ricerca attuale, niente seguito. Se lo è, parliamo del pilot da € 2.500.
          </p>
          <div className="mt-9 flex flex-col items-center justify-center gap-3 md:flex-row">
            <a
              href="mailto:info@normaai.org?subject=NormaAI%20demo%20call&body=Ciao%20Daniel%2C%0A%0AVorrei%20vedere%20NormaAI%20su%20un%20caso%20reale.%20Sono%20disponibile%3A%20%5Bmettere%202-3%20slot%5D.%0A%0AOrganizzazione%3A%0ARuolo%3A%0ATelefono%3A%0A%0AGrazie."
              className="inline-flex items-center gap-2 rounded-md bg-clay px-6 py-3 font-medium text-white transition hover:bg-clay-deep"
            >
              Scrivimi via email
              <ArrowRight className="h-4 w-4" />
            </a>
            <Link
              href="/login"
              className="inline-flex items-center gap-2 rounded-md border border-white/20 px-6 py-3 font-medium text-[#E8E6E0] transition hover:border-white/40 hover:text-white"
            >
              Hai già un account? Accedi
            </Link>
          </div>
        </div>
      </section>

      {/* ─────────────────── FOOTER ─────────────────── */}
      <footer className="border-t border-line bg-paper">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-6 py-10 text-sm text-night-3 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded bg-night font-serif text-xs text-paper">
              N
            </div>
            <span>NormaAI © {new Date().getFullYear()}</span>
          </div>
          <div className="flex flex-wrap gap-5">
            <Link href="/metodo" className="transition hover:text-night">Metodo</Link>
            <Link href="/privacy" className="transition hover:text-night">Privacy</Link>
            <Link href="/cookie" className="transition hover:text-night">Cookie</Link>
            <Link href="/terms" className="transition hover:text-night">Termini</Link>
            <Link href="/security" className="transition hover:text-night">Sicurezza</Link>
            <a href="mailto:info@normaai.org" className="transition hover:text-night">Contatti</a>
          </div>
        </div>
      </footer>
    </div>
  )
}

// ───────────────────────── Sub-components ─────────────────────────

function CodexForm() {
  const [status, setStatus] = useState<FormStatus>({ kind: 'idle' })

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (status.kind === 'submitting') return

    const fd = new FormData(e.currentTarget)
    // Outreach emails land on /codex?lead=<id> (redirected to /?lead=<id>);
    // forward that id so the founder notification ties back to the prospect.
    const leadRef =
      typeof window !== 'undefined'
        ? new URLSearchParams(window.location.search).get('lead') || undefined
        : undefined
    const payload = {
      email: String(fd.get('email') || '').trim(),
      org_name: String(fd.get('org') || '').trim() || undefined,
      role: String(fd.get('role') || '').trim() || undefined,
      source: 'codex_download',
      lead_ref: leadRef,
      website: String(fd.get('website') || ''), // honeypot
    }

    if (!payload.email || !/.+@.+\..+/.test(payload.email)) {
      setStatus({ kind: 'error', message: 'Inserisci un indirizzo email valido.' })
      return
    }

    setStatus({ kind: 'submitting' })

    try {
      const res = await fetch(LEADS_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
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
            'Richiesta registrata. Riceverai il Codex entro 24 ore.',
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
          'Impossibile contattare il server. Riprova tra qualche minuto, oppure scrivi a info@normaai.org con oggetto "Codex" e te lo mandiamo a mano.',
      })
    }
  }

  if (status.kind === 'success') {
    return (
      <div className="rounded-xl border border-emerald-600/30 bg-white p-6 shadow-[0_1px_2px_rgba(20,20,19,0.05)]">
        <div className="flex items-start gap-3">
          <div className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-emerald-600/10 text-emerald-700">
            <CheckCircle2 className="h-5 w-5" />
          </div>
          <div className="flex-1">
            <h3 className="font-serif text-xl text-night">Richiesta ricevuta</h3>
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

        <p className="mt-4 text-xs text-night-3">
          Il link è personale e funziona per 30 giorni. Nel frattempo, vuoi parlarne 30 min?{' '}
          <a
            href="mailto:info@normaai.org?subject=NormaAI%20demo%20call"
            className="font-medium text-clay hover:text-clay-deep"
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
      className="rounded-xl border border-line bg-white p-6 shadow-[0_1px_2px_rgba(20,20,19,0.05)]"
      onSubmit={handleSubmit}
      noValidate
    >
      {/* Honeypot: invisible to humans, bots fill it and get silently dropped */}
      <input
        type="text"
        name="website"
        tabIndex={-1}
        autoComplete="off"
        aria-hidden="true"
        className="absolute -left-[9999px] h-0 w-0 opacity-0"
      />
      <label className="block text-sm font-medium text-night">Email aziendale</label>
      <input
        name="email"
        type="email"
        required
        autoComplete="email"
        placeholder="nome@azienda.it"
        disabled={status.kind === 'submitting'}
        className="mt-2 w-full rounded-md border border-line bg-paper px-3 py-2.5 text-night placeholder:text-night-3 outline-none transition focus:border-clay disabled:opacity-60"
      />
      <label className="mt-4 block text-sm font-medium text-night">Nome organizzazione</label>
      <input
        name="org"
        autoComplete="organization"
        placeholder="Es: Acme S.p.A."
        disabled={status.kind === 'submitting'}
        className="mt-2 w-full rounded-md border border-line bg-paper px-3 py-2.5 text-night placeholder:text-night-3 outline-none transition focus:border-clay disabled:opacity-60"
      />
      <label className="mt-4 block text-sm font-medium text-night">Ruolo</label>
      <select
        name="role"
        defaultValue="Compliance Officer / DPO"
        disabled={status.kind === 'submitting'}
        className="mt-2 w-full rounded-md border border-line bg-paper px-3 py-2.5 text-night outline-none transition focus:border-clay disabled:opacity-60"
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
            Invio in corso…
          </>
        ) : (
          'Scarica il Codex'
        )}
      </button>
      {status.kind === 'error' && (
        <div
          role="alert"
          className="mt-3 flex items-start gap-2 rounded-md border border-red-700/30 bg-red-50 px-3 py-2 text-xs text-red-800"
        >
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>{status.message}</span>
        </div>
      )}
      <p className="mt-3 text-xs leading-relaxed text-night-3">
        Niente newsletter automatiche. Solo il PDF + un follow-up manuale per
        capire se NormaAI può servirvi davvero.
      </p>
    </form>
  )
}

// ICPCardV2: trifurcato per H1/H2/H3 (compliance officer / studio legale / CFO banca-assicurazione)
// Ogni card mostra: tag colorato + audience + pain (sotto cofano) + solution + CTA specifica
function ICPCardV2({
  tag,
  tagColor,
  audience,
  pain,
  solution,
  cta,
  ctaHref,
}: {
  tag: string
  tagColor: string
  audience: string
  pain: string
  solution: string
  cta: string
  ctaHref: string
}) {
  return (
    <div className="flex flex-col rounded-xl border border-line bg-white p-6 shadow-[0_1px_2px_rgba(20,20,19,0.04)] transition-all duration-200 hover:-translate-y-0.5 hover:border-line-2 hover:shadow-[0_8px_24px_-8px_rgba(20,20,19,0.12)]">
      <div className="flex items-center gap-2">
        <span
          className="inline-block h-2 w-2 rounded-full"
          style={{ backgroundColor: tagColor }}
        />
        <span
          className="text-xs font-semibold uppercase tracking-wider"
          style={{ color: tagColor }}
        >
          {tag}
        </span>
      </div>
      <div className="mt-1 text-xs text-night-3">{audience}</div>
      <div className="mt-4 flex items-start gap-2">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-night-3" />
        <p className="text-sm leading-relaxed text-night-2">{pain}</p>
      </div>
      <div className="mt-3 flex items-start gap-2">
        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-clay" />
        <p className="text-sm leading-relaxed text-night">{solution}</p>
      </div>
      <a
        href={ctaHref}
        className="mt-5 inline-flex items-center gap-1 text-sm font-medium text-clay transition hover:text-clay-deep"
      >
        {cta}
      </a>
    </div>
  )
}

// Framework brand hues, darkened for legibility on warm paper
// (the dashboard keeps the original neon set on dark).
const FW_COLOR: Record<string, string> = {
  CSRD: '#1F7A53',
  CSDDD: '#1D6FB8',
  'AI Act': '#7C4DBC',
  DORA: '#C05621',
  NIS2: '#A16A0B',
  'EU Taxonomy': '#0F766E',
  GDPR: '#C53048',
  ESRS: '#6B5CA5',
  CRA: '#C2613F',
}

function FwCard({
  tag,
  name,
  note,
  highlight,
}: {
  tag: string
  name: string
  note: string
  highlight?: boolean
}) {
  const color = FW_COLOR[tag] || '#C2613F'
  return (
    <div
      className={`rounded-xl border bg-white p-4 shadow-[0_1px_2px_rgba(20,20,19,0.04)] transition hover:border-line-2 ${
        highlight ? 'border-clay/50' : 'border-line'
      }`}
    >
      <div className="flex items-center gap-2">
        <span
          className="inline-block h-2 w-2 rounded-full"
          style={{ backgroundColor: color }}
        />
        <span
          className="text-xs font-semibold tracking-wider"
          style={{ color }}
        >
          {tag}
        </span>
      </div>
      <div className="mt-1.5 text-sm font-medium text-night">{name}</div>
      <div className="mt-1 text-xs text-night-3">{note}</div>
    </div>
  )
}

function UseCase({
  n,
  title,
  body,
  points,
}: {
  n: string
  title: string
  body: string
  points: string[]
}) {
  return (
    <div className="rounded-xl border border-line bg-white p-6 shadow-[0_1px_2px_rgba(20,20,19,0.04)] transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[0_8px_24px_-8px_rgba(20,20,19,0.12)]">
      <div className="font-serif text-3xl text-clay">{n}</div>
      <h3 className="mt-3 font-serif text-xl text-night">{title}</h3>
      <p className="mt-3 text-sm leading-relaxed text-night-2">{body}</p>
      <ul className="mt-4 space-y-1.5 text-sm">
        {points.map((p) => (
          <li key={p} className="flex items-start gap-2 text-night-2">
            <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-clay" />
            {p}
          </li>
        ))}
      </ul>
    </div>
  )
}

function ProofRow({
  icon,
  title,
  body,
}: {
  icon: React.ReactNode
  title: string
  body: string
}) {
  return (
    <div className="flex gap-4 rounded-xl border border-line bg-white p-5 shadow-[0_1px_2px_rgba(20,20,19,0.04)] transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[0_8px_24px_-8px_rgba(20,20,19,0.12)]">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-clay-soft text-clay">
        {icon}
      </div>
      <div>
        <h3 className="font-semibold text-night">{title}</h3>
        <p className="mt-1 text-sm leading-relaxed text-night-2">{body}</p>
      </div>
    </div>
  )
}
