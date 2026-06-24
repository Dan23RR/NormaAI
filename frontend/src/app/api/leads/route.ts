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
  website?: unknown // honeypot - humans never fill it
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
  if (clean(body.website)) {
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
      subject: `[NormaAI lead] ${email}${orgName ? ` - ${orgName}` : ''}`,
      text: [
        'Nuovo lead dal form Codex (route serverless Vercel):',
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

    // Codex delivery to the lead (best-effort; download link is already
    // in the HTTP response, so a failure here costs nothing).
    await sendResendEmail({
      apiKey,
      from,
      to: [email],
      subject: 'Il tuo Codex Post-Omnibus 2025-2029 - NormaAI',
      text: [
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
        'Domande su un caso concreto? Rispondi a questa email: 30 minuti,',
        'senza impegno.',
        '',
        'Daniel Culotta · NormaAI · info@normaai.org',
        '',
        '--',
        'Ricevi questa email perché hai richiesto il Codex dal nostro sito.',
        'Usiamo i tuoi dati solo per inviarti il Codex e ricontattarti su questo',
        'tema (legittimo interesse, GDPR Art. 6.1.f). Puoi opporti in ogni momento',
        'rispondendo a questa email.',
      ].join('\n'),
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
