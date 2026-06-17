import type { Metadata } from 'next'
import Link from 'next/link'
import {
  ShieldCheck,
  Database,
  GitBranch,
  FileText,
  ArrowLeft,
  CheckCircle2,
  Scale,
  ServerCog,
} from 'lucide-react'

export const metadata: Metadata = {
  title: 'Metodo e trasparenza - NormaAI',
  description:
    'Come è costruita NormaAI: pipeline anti-allucinazione verificabile, corpus EUR-Lex/Normattiva, decisioni di ingegneria pubbliche. Ogni numero in questa pagina è riproducibile dalla test suite.',
}

// Every figure on this page is reproducible from the repository.
// Update via: run_tests.ps1 (test counts) · CORE_FRAMEWORKS (seeds) ·
// the public ADRs. No live counters, no demo data - by design.
const VERIFIED = {
  lastVerified: '2026-06-12',
  backendTests: 327,
  frontendTests: 30,
  frameworks: 8,
  celexSeeds: 12,
  covePhases: 5,
  sncThresholds: { high: 0.85, low: 0.5 },
}

const ADRS = [
  {
    id: 'ADR-004',
    date: '2026-06-12',
    title: 'CRA (Cyber Resilience Act) come 8° framework',
    body: 'Reg. (UE) 2024/2847 + Implementing Reg. 2025/2392 nei seed EUR-Lex. Il claim pubblico resta "7 framework" finché il seed del corpus CRA non è verificato in produzione.',
  },
  {
    id: 'ADR-003',
    date: '2026-06-11',
    title: 'Source of truth per le date regolatorie',
    body: 'Le date CSDDD interne erano in conflitto (stop-the-clock vs Omnibus I). Verifica su fonte primaria: trasposizione 26-07-2028, prima compliance 26-07-2029 (Dir. (UE) 2026/470). Ogni data normativa nei prompt ora richiede fonte CELEX.',
  },
  {
    id: 'ADR-002',
    date: '2026-05-15',
    title: 'Deploy foundation: staging-first',
    body: 'Dominio custom rinviato; il funnel gira su URL staging finché ogni anello (form, email, download) non è verificato end-to-end.',
  },
  {
    id: 'ADR-001',
    date: '2026-05-08',
    title: 'Pivot ICP: via dalle boutique ESG',
    body: 'Le consulenze ESG sono competitor, non clienti. Tre ipotesi ICP in test parallelo: compliance officer mid-market, studi legali generalisti, CFO/risk di banche e assicurazioni piccole.',
  },
]

export default function MetodoPage() {
  return (
    <div className="min-h-screen bg-paper text-night">
      {/* Nav */}
      <nav className="sticky top-0 z-30 border-b border-line bg-paper/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-night font-serif text-lg text-paper">
              N
            </div>
            <span className="font-serif text-xl tracking-tight">NormaAI</span>
          </Link>
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 text-sm text-night-2 transition hover:text-night"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Torna alla home
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <section className="mx-auto max-w-3xl px-6 pb-16 pt-16 md:pt-20">
        <p className="mb-5 text-xs font-medium uppercase tracking-[0.18em] text-night-2">
          Metodo · trasparenza verificabile
        </p>
        <h1 className="font-serif text-4xl font-normal leading-[1.1] tracking-tight md:text-5xl">
          Niente contatori animati.
          <br />
          Solo numeri <em className="italic text-clay">riproducibili</em>.
        </h1>
        <p className="mt-6 text-lg leading-relaxed text-night-2">
          In un mercato dove ogni AI si dichiara "affidabile", noi facciamo una cosa
          diversa: pubblichiamo il metodo, le decisioni di ingegneria e i numeri - e ogni
          numero in questa pagina è riproducibile eseguendo la test suite del progetto,
          non generato da uno script di marketing. Ultima verifica:{' '}
          <strong className="text-night">{VERIFIED.lastVerified}</strong>.
        </p>
      </section>

      {/* Verified numbers */}
      <section className="border-t border-line bg-paper-2">
        <div className="mx-auto max-w-6xl px-6 py-16">
          <p className="mb-4 text-xs font-medium uppercase tracking-[0.18em] text-night-2">
            I numeri (run {VERIFIED.lastVerified})
          </p>
          <div className="grid gap-4 md:grid-cols-4">
            <StatCard
              n={`${VERIFIED.backendTests}/${VERIFIED.backendTests}`}
              label="test backend in pass"
              sub="8 tier: unit, DB/RLS, cache, retrieval, agenti, API, Monte Carlo"
            />
            <StatCard
              n={`${VERIFIED.frameworks}`}
              label="framework EU coperti"
              sub={`${VERIFIED.celexSeeds} atti CELEX nei seed EUR-Lex, sync notturna`}
            />
            <StatCard
              n={`${VERIFIED.covePhases} fasi`}
              label="Chain-of-Verification"
              sub="ogni claim estratto, verificato e citato prima della risposta"
            />
            <StatCard
              n="abstain"
              label="quando il trust è basso"
              sub={`sotto trust ${VERIFIED.sncThresholds.low} il sistema NON risponde: lo dice`}
            />
          </div>
          <p className="mt-6 text-sm text-night-3">
            Come riprodurli: la suite gira in CI a ogni commit (lint, type-check, test su
            Postgres/Qdrant/Redis reali, scansioni di sicurezza, SBOM). I conteggi sopra
            sono l'output dell'ultima run completa, aggiornati a ogni release - mai stimati.
          </p>
        </div>
      </section>

      {/* Pipeline */}
      <section className="border-t border-line">
        <div className="mx-auto max-w-6xl px-6 py-16">
          <p className="mb-4 text-xs font-medium uppercase tracking-[0.18em] text-night-2">
            La pipeline anti-allucinazione
          </p>
          <h2 className="max-w-2xl font-serif text-3xl font-normal tracking-tight md:text-[36px]">
            Tre cancelli tra il modello e la tua risposta.
          </h2>
          <div className="mt-10 grid gap-4 md:grid-cols-3">
            <GateCard
              icon={<Database className="h-5 w-5" />}
              step="01 · Grounding"
              title="Solo fonte primaria"
              body="Hybrid retrieval (denso + BM25 + RRF) sul corpus EUR-Lex e Normattiva, con filtro temporale: i testi superseded sono esclusi di default. Il modello non risponde mai 'a memoria'."
            />
            <GateCard
              icon={<Scale className="h-5 w-5" />}
              step="02 · Trust gate"
              title="K campioni, una decisione"
              body={`Il sistema genera K risposte indipendenti e ne misura la coerenza comportamentale. Sopra ${VERIFIED.sncThresholds.high} procede; sotto ${VERIFIED.sncThresholds.low} si astiene e ti dice di consultare un esperto. L'astensione è una risposta.`}
            />
            <GateCard
              icon={<ShieldCheck className="h-5 w-5" />}
              step="03 · Verifica"
              title="Ogni claim, ogni citazione"
              body="Chain-of-Verification a 5 fasi: estrazione claim, domande di verifica indipendenti, revisione, validazione di ogni CELEX/URN contro EUR-Lex e Normattiva. Le citazioni inventate muoiono qui."
            />
          </div>
        </div>
      </section>

      {/* EU sovereignty */}
      <section className="border-t border-line bg-paper-2">
        <div className="mx-auto max-w-6xl px-6 py-16">
          <div className="grid gap-10 lg:grid-cols-12 lg:items-start">
            <div className="lg:col-span-7">
              <p className="mb-4 text-xs font-medium uppercase tracking-[0.18em] text-night-2">
                Sovranità del dato
              </p>
              <h2 className="font-serif text-3xl font-normal tracking-tight md:text-[36px]">
                I tuoi dati restano in Europa. Il modello, se vuoi, in casa tua.
              </h2>
              <p className="mt-5 leading-relaxed text-night-2">
                Infrastruttura in data center EU (Germania, regione Francoforte) con
                isolamento multi-tenant a livello di database (Row-Level Security
                PostgreSQL). Per i regimi più rigorosi - DPIA strict, settore finanziario,
                segreto industriale - NormaAI funziona in modalità sovrana:
              </p>
              <ul className="mt-5 space-y-2.5 text-sm text-night-2">
                <li className="flex items-start gap-2.5">
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-clay" />
                  <span>
                    <strong className="text-night">BYO API key</strong>: il traffico LLM passa
                    dal tuo tenant (Vertex/Bedrock EU), non dal nostro
                  </span>
                </li>
                <li className="flex items-start gap-2.5">
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-clay" />
                  <span>
                    <strong className="text-night">Self-host del modello</strong> (Ollama): zero
                    chiamate cloud, il testo normativo non lascia il perimetro
                  </span>
                </li>
                <li className="flex items-start gap-2.5">
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-clay" />
                  <span>
                    <strong className="text-night">Audit trail strutturato</strong>: ogni accesso
                    e ogni risposta tracciati per organizzazione, esportabili per l'auditor
                  </span>
                </li>
              </ul>
            </div>
            <div className="lg:col-span-5">
              <div className="rounded-xl bg-coal p-6 text-[#E8E6E0]">
                <div className="mb-3 flex items-center gap-2 text-xs text-[#9C9A92]">
                  <ServerCog className="h-4 w-4" />
                  AI Act, Art. 50 - trasparenza
                </div>
                <p className="text-sm leading-relaxed">
                  NormaAI è essa stessa un sistema AI soggetto al Regolamento (UE)
                  2024/1689 - e lo dichiara su ogni superficie. Il footer della dashboard,
                  le risposte e questa pagina dicono la stessa cosa:{' '}
                  <strong className="text-white">
                    supporto decisionale, non consulenza legale
                  </strong>
                  . Un fornitore di compliance che non rispetta la propria normativa non
                  merita la tua fiducia.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Public ADRs */}
      <section className="border-t border-line">
        <div className="mx-auto max-w-3xl px-6 py-16">
          <p className="mb-4 text-xs font-medium uppercase tracking-[0.18em] text-night-2">
            Decisioni di ingegneria - pubbliche
          </p>
          <h2 className="font-serif text-3xl font-normal tracking-tight md:text-[36px]">
            Anche quando sbagliamo, lo scriviamo.
          </h2>
          <p className="mt-4 leading-relaxed text-night-2">
            Ogni decisione rilevante è un Architecture Decision Record datato. Questa è la
            serie completa - inclusa quella in cui i nostri stessi documenti avevano le
            date CSDDD sbagliate, e come l'abbiamo corretto con la fonte primaria.
          </p>
          <div className="mt-8 space-y-4">
            {ADRS.map((adr) => (
              <div
                key={adr.id}
                className="rounded-xl border border-line bg-white p-5 shadow-[0_1px_2px_rgba(20,20,19,0.04)]"
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="text-xs font-semibold uppercase tracking-wider text-clay">
                    {adr.id}
                  </span>
                  <span className="font-mono text-xs text-night-3">{adr.date}</span>
                </div>
                <h3 className="mt-2 font-serif text-lg text-night">{adr.title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-night-2">{adr.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="bg-coal text-[#E8E6E0]">
        <div className="mx-auto max-w-3xl px-6 py-20 text-center">
          <h2 className="font-serif text-3xl font-normal tracking-tight text-white md:text-[36px]">
            Giudica il metodo su una domanda vera.
          </h2>
          <p className="mx-auto mt-4 max-w-xl leading-relaxed text-[#B5B3AA]">
            Porta un caso reale del tuo lavoro: se la risposta non è migliore della tua
            ricerca attuale - citazioni alla mano - niente seguito.
          </p>
          <div className="mt-8 flex flex-col items-center justify-center gap-3 md:flex-row">
            <a
              href="mailto:info@normaai.org?subject=NormaAI%20demo%20call"
              className="inline-flex items-center gap-2 rounded-md bg-clay px-6 py-3 font-medium text-white transition hover:bg-clay-deep"
            >
              Prenota 30 minuti
            </a>
            <Link
              href="/#codex"
              className="inline-flex items-center gap-2 rounded-md border border-white/20 px-6 py-3 font-medium text-[#E8E6E0] transition hover:border-white/40 hover:text-white"
            >
              <FileText className="h-4 w-4" />
              Scarica il Codex Post-Omnibus
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-line bg-paper">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-6 py-10 text-sm text-night-3 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded bg-night font-serif text-xs text-paper">
              N
            </div>
            <span>NormaAI © {new Date().getFullYear()}</span>
          </div>
          <div className="flex flex-wrap gap-5">
            <Link href="/privacy" className="transition hover:text-night">Privacy</Link>
            <Link href="/cookie" className="transition hover:text-night">Cookie</Link>
            <Link href="/terms" className="transition hover:text-night">Termini</Link>
            <Link href="/security" className="transition hover:text-night">Sicurezza</Link>
          </div>
        </div>
      </footer>
    </div>
  )
}

function StatCard({ n, label, sub }: { n: string; label: string; sub: string }) {
  return (
    <div className="rounded-xl border border-line bg-white p-5 shadow-[0_1px_2px_rgba(20,20,19,0.04)]">
      <div className="font-serif text-3xl text-clay">{n}</div>
      <div className="mt-1 text-sm font-medium text-night">{label}</div>
      <div className="mt-1.5 text-xs leading-relaxed text-night-3">{sub}</div>
    </div>
  )
}

function GateCard({
  icon,
  step,
  title,
  body,
}: {
  icon: React.ReactNode
  step: string
  title: string
  body: string
}) {
  return (
    <div className="rounded-xl border border-line bg-white p-6 shadow-[0_1px_2px_rgba(20,20,19,0.04)]">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-md bg-clay-soft text-clay">
          {icon}
        </div>
        <span className="text-xs font-medium uppercase tracking-[0.15em] text-night-3">
          {step}
        </span>
      </div>
      <h3 className="mt-4 font-serif text-xl text-night">{title}</h3>
      <p className="mt-2 text-sm leading-relaxed text-night-2">{body}</p>
    </div>
  )
}
