'use client'

import { Shield, Lock, Eye, Server, FileCheck, AlertTriangle } from 'lucide-react'
import { LegalLayout } from '@/components/LegalLayout'

const SECURITY_SECTIONS = [
  {
    icon: Lock,
    title: 'Crittografia',
    items: [
      'Dati in transito: TLS 1.3 su tutte le connessioni',
      'Dati at rest: AES-256 su PostgreSQL e backup',
      'Token di autenticazione: JWT RS256 con rotazione automatica',
      'Password: bcrypt con salt individuale (work factor 12)',
    ],
  },
  {
    icon: Shield,
    title: 'Controllo Accessi',
    items: [
      'Multi-tenant isolation via PostgreSQL Row Level Security (RLS)',
      'RBAC granulare: 24 permessi su 9 moduli, ruoli personalizzabili',
      'Segregazione dei compiti (four-eyes principle) per approvazioni',
      'SSO enterprise: SAML 2.0 / OpenID Connect (Okta, Azure AD, Google)',
      'Rate limiting per endpoint con sliding window',
      'JTI blacklist per revoca immediata token',
    ],
  },
  {
    icon: Eye,
    title: 'Audit & Monitoraggio',
    items: [
      'Audit trail completo: 17+ eventi tracciati con timestamp, utente, IP',
      'Retention audit log: 7+ anni (requisito Basel III / MiFID II)',
      'Export audit report per regolatori: CSV con filtri avanzati',
      'Monitoraggio real-time: health check, latency tracking, error rate',
    ],
  },
  {
    icon: Server,
    title: 'Infrastruttura',
    items: [
      'Architettura: FastAPI (Python) + Next.js 14 (TypeScript)',
      'Database: PostgreSQL con RLS multi-tenant',
      'Vector DB: Qdrant per ricerca semantica normativa',
      'Cache: Redis per session management e rate limiting',
      'LLM: Google Gemini 2.5 Flash via API (data processing agreement attivo)',
      'CORS hardened con whitelist origini',
    ],
  },
  {
    icon: FileCheck,
    title: 'Conformità & Trasparenza AI',
    items: [
      'AI Act Art. 50: disclosure sistema AI su ogni output',
      'GDPR Art. 28: sub-responsabili documentati (Google Gemini, Resend, Hetzner) + DPA template per i clienti',
      'Disclaimer legale persistente su ogni pagina',
      'Confidence score qualitativo (non percentuale fuorviante)',
      'Badge "Verifica sempre raccomandata" su ogni analisi AI',
      'Termini di Servizio e Privacy Policy pubblicati',
    ],
  },
  {
    icon: AlertTriangle,
    title: 'Incident Response & Breach Notification',
    items: [
      'Notifica al cliente (Titolare) senza ingiustificato ritardo e comunque entro 48h dalla conoscenza della violazione',
      'Contenuto minimo ex Art. 33(3) GDPR: natura, categorie e numero interessati, conseguenze probabili, misure adottate',
      'Coordinamento con il Titolare per gli adempimenti Art. 33 (Autorità, 72h) e Art. 34 (interessati)',
      'Runbook di incident response e canale dedicato security@normaai.org',
      'Clausola di breach notification inclusa nel DPA (Art. 28) fornito ai clienti',
    ],
  },
]

export default function SecurityPage() {
  return (
    <LegalLayout
      title="Sicurezza"
      intro="Panoramica dei controlli di sicurezza, conformità e protezione dati. Cosa NormaAI fa per proteggere i tuoi dati."
      lastUpdated="Marzo 2026 · NormaAI v0.3"
    >
      {/* SOC 2 Badge */}
      <div className="rounded-xl border border-clay/40 bg-white p-5">
        <div className="flex items-start gap-4">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-clay/40 bg-clay-soft">
            <Shield className="h-6 w-6 text-clay" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-night">SOC 2 Type II</h2>
              <span className="rounded-full border border-warn/30 bg-warn/10 px-2 py-0.5 text-[10px] font-medium text-warn">
                In Progress
              </span>
            </div>
            <p className="mt-1 text-xs text-night-2">
              NormaAI sta completando il percorso di certificazione SOC 2 Type II. Audit di
              sicurezza, penetration testing e documentazione completa dei controlli.
            </p>
          </div>
        </div>
      </div>

      {/* Security sections */}
      {SECURITY_SECTIONS.map((section) => {
        const Icon = section.icon
        return (
          <section
            key={section.title}
            className="rounded-xl border border-line bg-white p-5 transition hover:border-line-2"
          >
            <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-night">
              <Icon className="h-4 w-4 text-clay" />
              {section.title}
            </h3>
            <ul className="space-y-2">
              {section.items.map((item, i) => (
                <li key={i} className="flex items-start gap-2 text-xs text-night-2">
                  <span className="mt-0.5 shrink-0 text-clay">•</span>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </section>
        )
      })}

      {/* Contact */}
      <div className="rounded-xl border border-line bg-white p-5">
        <h3 className="mb-2 text-sm font-semibold text-night">
          Security Questionnaire & Contatti
        </h3>
        <p className="text-xs leading-relaxed text-night-2">
          Per richieste relative alla sicurezza, questionari vendor, o segnalazioni di
          vulnerabilità:
        </p>
        <p className="mt-2 text-sm font-medium">
          <a
            href="mailto:security@normaai.org"
            className="text-clay transition hover:text-clay-deep"
          >
            security@normaai.org
          </a>
        </p>
        <p className="mt-2 text-[10px] text-night-2">
          Tempo di risposta target: 24h lavorative per questionari, 4h per segnalazioni di
          vulnerabilità.
        </p>
      </div>
    </LegalLayout>
  )
}
