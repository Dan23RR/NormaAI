import { NextRequest, NextResponse } from 'next/server'
import { LOCALE_COOKIE, toLanguage } from '@/i18n/config'
import { MAX_BODY_BYTES, checkLead, clientIp, createRateLimiter, honeypotFilled, plainText } from '@/lib/leads'

/**
 * Serverless lead capture. Every public form (landing, /codex, the static
 * scope checkers) posts here, same-origin, so the funnel never depends on
 * the FastAPI backend being up.
 *
 * The response carries the address of the Codex, which the forms show as a
 * download button: nothing is ever emailed to the address typed in the form,
 * so the route cannot be used to make the site write to anybody. The only
 * email is the notification to the operator's own inbox, when configured.
 *
 * Env (Vercel → Project Settings → Environment Variables, server-side):
 *   RESEND_API_KEY      optional - enables the notification to the operator
 *   LEADS_NOTIFY_EMAIL  optional - operator inbox (default info@normaai.org)
 *   RESEND_FROM_EMAIL   optional - verified sender (default info@normaai.org)
 *
 * Design rule: NEVER lose a lead. If Resend is missing or fails, we still
 * log the lead (Vercel function logs) and return the download link.
 */

const CODEX_PATH = '/codex-post-omnibus-2025-2029.pdf'

// Requests per client address in one hour, per warm instance of the function
// (lib/leads.ts says why this is best effort). Enough for a person who tries
// the two checkers and the Codex form a few times; the forms say "try again
// in an hour" on a 429.
const PER_IP = createRateLimiter({ limit: 10, windowMs: 60 * 60 * 1000 })

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
  // The landing form shows `message` and `detail` as they are, so they follow
  // the interface language (the `normaai.locale` cookie, Italian by default).
  // The two static checkers are Italian only and do not show them.
  const english = toLanguage(req.cookies.get(LOCALE_COOKIE)?.value) === 'en'
  const invalid = (detail: { it: string; en: string }, status = 422) =>
    NextResponse.json({ detail: english ? detail.en : detail.it }, { status })
  const INVALID_BODY = { it: 'Richiesta non valida.', en: 'Invalid request.' }

  // Every request counts, the ones a bot fills in included.
  const limit = PER_IP.hit(clientIp(req.headers))
  if (!limit.allowed) {
    return NextResponse.json(
      {
        detail: english
          ? 'Too many recent requests from the same address. Try again in an hour.'
          : 'Troppe richieste recenti dallo stesso indirizzo. Riprova tra un’ora.',
      },
      { status: 429, headers: { 'Retry-After': String(limit.retryAfterSeconds) } },
    )
  }

  const tooLarge = { it: 'Richiesta troppo grande.', en: 'Request too large.' }
  if (Number(req.headers.get('content-length') ?? 0) > MAX_BODY_BYTES) return invalid(tooLarge, 413)
  let raw: string
  try {
    raw = await req.text()
  } catch {
    return invalid(INVALID_BODY)
  }
  if (new TextEncoder().encode(raw).length > MAX_BODY_BYTES) return invalid(tooLarge, 413)
  let body: unknown
  try {
    body = JSON.parse(raw)
  } catch {
    return invalid(INVALID_BODY)
  }

  // Honeypot: pretend success so bots stop retrying, deliver nothing.
  // Logged first: a human whose browser autofilled the hidden field would
  // otherwise vanish without a trace ("NEVER lose a lead" applies here too).
  if (body && typeof body === 'object' && !Array.isArray(body) && honeypotFilled(body as Record<string, unknown>)) {
    const b = body as Record<string, unknown>
    console.log(
      JSON.stringify({
        event: 'lead_honeypot',
        email: plainText(b.email, 254),
        source: plainText(b.source, 80),
        lead_ref: plainText(b.lead_ref, 80),
        ts: new Date().toISOString(),
      }),
    )
    return NextResponse.json(
      { message: english ? 'Request recorded.' : 'Richiesta registrata.' },
      { status: 200 },
    )
  }

  const checked = checkLead(body)
  if (!checked.ok) {
    return checked.field === 'email'
      ? invalid({ it: 'Indirizzo email non valido.', en: 'Invalid email address.' })
      : invalid(INVALID_BODY)
  }
  const { email, orgName, role, source, leadRef } = checked.lead

  // Always log - this is the persistence floor if email is unavailable.
  console.log(
    JSON.stringify({
      event: 'lead_captured',
      email,
      org_name: orgName,
      role,
      lead_ref: leadRef,
      source,
      ts: new Date().toISOString(),
    }),
  )

  const apiKey = process.env.RESEND_API_KEY
  const from = process.env.RESEND_FROM_EMAIL || 'NormaAI <info@normaai.org>'
  const notifyTo = process.env.LEADS_NOTIFY_EMAIL || 'info@normaai.org'

  if (apiKey) {
    // The one email: to the operator's inbox, never to the address in the
    // form, which is only the reply-to. The source carries the checker's
    // band and, for the AI Act, the situations ticked, so a reply can name
    // the passages of law that concern them without asking again.
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
  }

  // The message says only what happened: the request is recorded and the
  // response carries the link, which the form shows as a download button.
  return NextResponse.json(
    {
      message: english
        ? 'Request recorded. Download the Codex with the button below.'
        : 'Richiesta registrata. Scarica il Codex con il pulsante qui sotto.',
      download_url: CODEX_PATH,
    },
    { status: 200 },
  )
}
