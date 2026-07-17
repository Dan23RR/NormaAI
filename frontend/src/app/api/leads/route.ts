import { NextRequest, NextResponse } from 'next/server'

/**
 * Serverless lead capture - keeps the Codex funnel alive while the
 * FastAPI backend (api.normaai.org) is not deployed yet.
 *
 * The landing form posts here ONLY when NEXT_PUBLIC_API_URL is unset
 * (same-origin fallback). Once the backend is live, set that env var on
 * Vercel and traffic flows to /api/v1/leads with the full pipeline
 * (HMAC links, Postgres, suppression list) - this route stays as backup.
 *
 * Env (Vercel → Project Settings → Environment Variables, server-side):
 *   RESEND_API_KEY      optional - enables email notification + delivery
 *   LEADS_NOTIFY_EMAIL  optional - founder inbox (default info@normaai.org)
 *   RESEND_FROM_EMAIL   optional - verified sender (default info@normaai.org)
 *
 * Design rule: NEVER lose a lead. If Resend is missing or fails, we still
 * log the lead (Vercel function logs) and return the download link.
 */

const CODEX_PATH = '/codex-post-omnibus-2025-2029.pdf'
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/

type LeadPayload = {
  email?: unknown
  org_name?: unknown
  role?: unknown
  source?: unknown
  lead_ref?: unknown
  contact_time?: unknown // honeypot - humans never fill it (autofill-safe name)
  website?: unknown // legacy honeypot key (pages cached during a deploy still send it)
}

function clean(v: unknown, max = 200): string {
  return typeof v === 'string' ? v.trim().slice(0, max) : ''
}

async function sendResendEmail(opts: {
  apiKey: string
  from: string
  to: string[]
  subject: string
  text: string
  replyTo?: string
}): Promise<boolean> {
  try {
    const res = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${opts.apiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        from: opts.from,
        to: opts.to,
        subject: opts.subject,
        text: opts.text,
        ...(opts.replyTo ? { reply_to: opts.replyTo } : {}),
      }),
    })
    return res.ok
  } catch {
    return false
  }
}

export async function POST(req: NextRequest) {
  let body: LeadPayload
  try {
    body = (await req.json()) as LeadPayload
  } catch {
    return NextResponse.json({ detail: 'Invalid JSON body.' }, { status: 422 })
  }

  // Honeypot: pretend success so bots stop retrying, deliver nothing.
  // Logged first: a human whose browser autofilled the hidden field would
  // otherwise vanish without a trace ("NEVER lose a lead" applies here too).
  // Read both the new autofill-safe key and the legacy one, so a page cached
  // mid-deploy is still protected.
  if (clean(body.contact_time) || clean(body.website)) {
    console.log(
      JSON.stringify({
        event: 'lead_honeypot',
        email: clean(body.email),
        source: clean(body.source, 80),
        lead_ref: clean(body.lead_ref, 80),
        ts: new Date().toISOString(),
      }),
    )
    return NextResponse.json({ message: 'Richiesta registrata.' }, { status: 200 })
  }

  const email = clean(body.email)
  const orgName = clean(body.org_name)
  const role = clean(body.role, 80)
  const leadRef = clean(body.lead_ref, 80)
  const source = clean(body.source, 80) || 'codex_download'

  if (!EMAIL_RE.test(email)) {
    return NextResponse.json(
      { detail: 'Indirizzo email non valido.' },
      { status: 422 },
    )
  }

  const origin = req.nextUrl.origin
  const downloadUrl = CODEX_PATH // relative: form resolves same-origin

  // Always log - this is the persistence floor if email is unavailable.
  console.log(
    JSON.stringify({
      event: 'lead_captured',
      email,
      org_name: orgName || null,
      role: role || null,
      lead_ref: leadRef || null,
      source,
      ts: new Date().toISOString(),
    }),
  )

  const apiKey = process.env.RESEND_API_KEY
  const from = process.env.RESEND_FROM_EMAIL || 'NormaAI <info@normaai.org>'
  const notifyTo = process.env.LEADS_NOTIFY_EMAIL || 'info@normaai.org'

  if (apiKey) {
    // Founder notification - fire first, it's the one that matters.
    await sendResendEmail({
      apiKey,
      from,
      to: [notifyTo],
      subject: `[NormaAI lead${leadRef ? ` - ${leadRef}` : ''}] ${email}${orgName ? ` - ${orgName}` : ''}`,
      text: [
        'Nuovo lead dal sito (route serverless Vercel):',
        '',
        `Email:   ${email}`,
        `Org:     ${orgName || '-'}`,
        `Ruolo:   ${role || '-'}`,
        `LeadRef: ${leadRef || '- (traffico organico)'}`,
        `Source:  ${source}`,
        '',
        'NB: se il backend non è ancora live, il lead NON è in Postgres',
        'e va importato quando il backend viene deployato.',
      ].join('\n'),
      replyTo: email,
    })

    // Lead delivery email (best-effort; download link is already in the HTTP
    // response, so a failure here costs nothing). Branched per funnel: an AI
    // Act lead must NOT receive a CSRD-only first touchpoint - for a brand that
    // sells regulatory precision, the first email has to match the check done.
    const isAiAct = leadRef === 'scope-aiact'
    await sendResendEmail({
      apiKey,
      from,
      to: [email],
      subject: isAiAct
        ? 'Il tuo check AI Act (Art. 50) + Codex Post-Omnibus - NormaAI'
        : 'Il tuo Codex Post-Omnibus 2025-2029 - NormaAI',
      text: (isAiAct
        ? [
            "Grazie per l'interesse in NormaAI.",
            '',
            'Ho ricevuto il tuo check AI Act (Art. 50, Reg. UE 2024/1689): ti',
            'scrivo io, personalmente, con la lettura del tuo caso - chi è il',
            'destinatario di ogni obbligo, quali eccezioni valgono per voi e',
            'cosa predisporre prima del 2 agosto 2026.',
            '',
            'Se vuoi anticipare, rispondi a questa email: 20 minuti di',
            'confronto, senza impegno.',
            '',
            'In omaggio, come promesso, il Codex Post-Omnibus CSRD/CSDDD',
            '(PDF, 17 pagine - il quadro sostenibilità post-Omnibus I):',
            `${origin}${CODEX_PATH}`,
            '',
            'Daniel Culotta · NormaAI · info@normaai.org',
            '',
            '--',
            'Ricevi questa email perché hai usato il check AI Act sul nostro sito.',
            'Usiamo i tuoi dati solo per inviarti l\'analisi e ricontattarti su questo',
            'tema (legittimo interesse, GDPR Art. 6.1.f). Puoi opporti in ogni momento',
            'rispondendo a questa email.',
          ]
        : [
            "Grazie per l'interesse in NormaAI.",
            '',
            `Scarica il Codex Post-Omnibus 2025-2029 (PDF, 17 pagine):`,
            `${origin}${CODEX_PATH}`,
            '',
            'Dentro trovi: soglie CSRD post-Omnibus (1.000+ dipendenti e €450M,',
            'cumulativa), calendario CSDDD (trasposizione 26 luglio 2028,',
            'prima compliance luglio 2029 - Dir. (UE) 2026/470), flowchart',
            '"sono in scope?", e i 10 errori più comuni nelle prime disclosure.',
            '',
            'Domande su un caso concreto? Rispondi a questa email: 20 minuti,',
            'senza impegno.',
            '',
            'Daniel Culotta · NormaAI · info@normaai.org',
            '',
            '--',
            'Ricevi questa email perché hai richiesto il Codex dal nostro sito.',
            'Usiamo i tuoi dati solo per inviarti il Codex e ricontattarti su questo',
            'tema (legittimo interesse, GDPR Art. 6.1.f). Puoi opporti in ogni momento',
            'rispondendo a questa email.',
          ]
      ).join('\n'),
    })
  }

  return NextResponse.json(
    {
      message: 'Richiesta registrata. Il download parte subito qui sotto.',
      download_url: downloadUrl,
    },
    { status: 200 },
  )
}
