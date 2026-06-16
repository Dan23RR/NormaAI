"""Email client — Resend SDK with graceful fallback.

Free tier: 3000 email/month, 100/day. DKIM auto on verified domains.
Migrated from smtplib (G6.17) for:
  - Proper deliverability (DKIM/SPF/DMARC handled by provider)
  - Open + click tracking webhooks
  - No more sender drift (no more @gmail.com posing as founder)

Env vars (read via src.config.get_settings):
    RESEND_API_KEY         (required for actual sending)
    RESEND_FROM_EMAIL      (default: info@normaai.org)
    RESEND_FROM_NAME       (default: "Daniel Culotta — NormaAI")
    RESEND_REPLY_TO        (default: info@normaai.org)
    NORMAAI_PUBLIC_URL     (used to build absolute URLs)

Exposes two send paths:
    send_codex_email()       — inbound (post-form Codex download)
    send_outreach_email()    — outbound Wave 2 (cold + follow-up)

Both return (success, error_message) without raising.
"""

from __future__ import annotations

import os

import structlog

logger = structlog.get_logger()


# ─────────────────────────── Config ───────────────────────────


def _get_config() -> dict:
    return {
        "api_key": os.environ.get("RESEND_API_KEY", "").strip(),
        "from_email": os.environ.get("RESEND_FROM_EMAIL", "info@normaai.org").strip(),
        "from_name": os.environ.get("RESEND_FROM_NAME", "Daniel Culotta — NormaAI").strip(),
        "reply_to": os.environ.get("RESEND_REPLY_TO", "info@normaai.org").strip(),
        "public_url": os.environ.get("NORMAAI_PUBLIC_URL", "https://normaai.org").rstrip("/"),
    }


def email_configured() -> bool:
    return bool(_get_config()["api_key"])


def _from_header(cfg: dict) -> str:
    return f"{cfg['from_name']} <{cfg['from_email']}>"


# ─────────────────────────── Templates ───────────────────────────


def _codex_email_html(recipient_name: str, download_url: str) -> str:
    """Inbound Codex download — brand-consistent dark template."""
    name = recipient_name or "ciao"
    return f"""\
<!doctype html>
<html><body style="margin:0;padding:0;background:#0a0d12;color:#e6ebf2;font-family:Arial,sans-serif;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#0a0d12;padding:24px 12px;">
  <tr><td align="center">
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="600" style="background:#11161e;border-radius:12px;padding:28px 32px;max-width:600px;">
      <tr><td>
        <div style="display:inline-block;background:#5b8cff;color:#fff;font-weight:bold;width:34px;height:34px;line-height:34px;text-align:center;border-radius:8px;font-size:18px;">N</div>
        <span style="color:#e6ebf2;font-weight:600;font-size:16px;margin-left:10px;vertical-align:8px;">NormaAI</span>
      </td></tr>
      <tr><td style="padding:20px 0 0;">
        <h1 style="font-size:22px;color:#e6ebf2;margin:0 0 12px;font-weight:700;">Ecco il Codex Post-Omnibus.</h1>
        <p style="color:#aab3c0;font-size:14px;line-height:1.5;margin:0 0 16px;">
          Ciao {name}, grazie per la richiesta. Trovi qui il PDF (17 pagine, fonti EU/IT verificate al 28 aprile 2026).
        </p>
        <p style="margin:24px 0 8px;">
          <a href="{download_url}"
             style="display:inline-block;background:#5b8cff;color:#0a0d12;text-decoration:none;font-weight:600;padding:12px 22px;border-radius:8px;font-size:14px;">
            Scarica il Codex (PDF)
          </a>
        </p>
        <p style="color:#6f7a8a;font-size:12px;line-height:1.5;margin:16px 0 0;">
          Il link è personale e funziona per 30 giorni. Se ti serve di nuovo, scrivimi.
        </p>
      </td></tr>
      <tr><td style="padding:24px 0 0;border-top:1px solid rgba(255,255,255,0.08);margin-top:20px;">
        <p style="color:#aab3c0;font-size:13px;line-height:1.6;margin:16px 0 8px;">
          <b>Cosa puoi trovare nel Codex:</b>
        </p>
        <ul style="color:#aab3c0;font-size:13px;line-height:1.6;margin:0 0 16px 18px;padding:0;">
          <li>Soglie CSRD post-Omnibus verificate (1.000 dip + €450M turnover, AND cumulativa)</li>
          <li>Calendario CSDDD post-delay (transposition lug 2028, compliance lug 2029)</li>
          <li>I 10 errori più comuni nelle prime disclosure CSRD (con fix)</li>
          <li>Glossario operativo 30 termini con riferimenti normativi</li>
        </ul>
        <p style="color:#aab3c0;font-size:13px;line-height:1.6;margin:16px 0 0;">
          Se vuoi 30 minuti per parlare di un caso reale, rispondi a questa email.
          La call è gratuita e niente seguito se NormaAI non vi serve davvero.
        </p>
      </td></tr>
      <tr><td style="padding:24px 0 0;color:#6f7a8a;font-size:11px;">
        Daniel Culotta · NormaAI · info@normaai.org<br/>
        Disclaimer: il Codex è guida operativa, non parere legale.
      </td></tr>
    </table>
  </td></tr>
</table>
</body></html>
"""


def _codex_email_text(recipient_name: str, download_url: str) -> str:
    name = recipient_name or "ciao"
    return f"""Ciao {name},

Grazie per la richiesta. Ecco il Codex Post-Omnibus 2025-2029
(PDF 17 pagine, fonti EU/IT verificate al 28 aprile 2026).

Scarica qui (link valido 30 giorni):
{download_url}

Cosa trovi nel Codex:
- Soglie CSRD post-Omnibus verificate (1.000 dip + €450M turnover)
- Calendario CSDDD post-delay
- I 10 errori più comuni nelle prime disclosure CSRD
- Glossario operativo 30 termini con riferimenti normativi

Se vuoi 30 minuti per parlare di un caso reale, rispondi a questa email.
La call è gratuita.

Daniel Culotta
NormaAI · info@normaai.org

---
Disclaimer: guida operativa, non parere legale.
"""


# ─────────────────────────── Sender ───────────────────────────


def _send_via_resend(
    *,
    to_email: str,
    subject: str,
    html: str,
    text: str,
    headers: dict | None = None,
    tags: list[dict] | None = None,
) -> tuple[bool, str | None]:
    """Low-level Resend API call. Returns (success, error)."""
    cfg = _get_config()
    if not cfg["api_key"]:
        logger.warning("resend_not_configured", to=to_email)
        return False, "resend_not_configured"

    try:
        import resend  # type: ignore
    except ImportError:
        logger.error("resend_sdk_not_installed", note="pip install resend")
        return False, "resend_sdk_not_installed"

    resend.api_key = cfg["api_key"]
    payload = {
        "from": _from_header(cfg),
        "to": [to_email],
        "reply_to": cfg["reply_to"],
        "subject": subject,
        "html": html,
        "text": text,
    }
    if headers:
        payload["headers"] = headers
    if tags:
        payload["tags"] = tags

    try:
        response = resend.Emails.send(payload)
        message_id = (response or {}).get("id") if isinstance(response, dict) else None
        logger.info("resend_email_sent", to=to_email, message_id=message_id, subject=subject[:80])
        return True, None
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        logger.error("resend_email_failed", to=to_email, error=err)
        return False, err


def send_codex_email(
    to_email: str,
    recipient_name: str,
    download_url: str,
) -> tuple[bool, str | None]:
    """Inbound: send Codex download link to a lead from public form."""
    return _send_via_resend(
        to_email=to_email,
        subject="Il tuo Codex Post-Omnibus 2025-2029 (PDF)",
        html=_codex_email_html(recipient_name, download_url),
        text=_codex_email_text(recipient_name, download_url),
        tags=[{"name": "campaign", "value": "codex_inbound"}],
    )


def _outreach_compliance_footer(cfg: dict, *, cold: bool) -> str:
    """GDPR footer appended to every outbound email.

    Cold (first-touch) emails carry the full Art. 14 disclosure (data source +
    legitimate-interest basis); follow-ups carry a compact opt-out line. Both
    always pair with a List-Unsubscribe header (RFC 2369) set in
    send_outreach_email. Injected centrally so the Wave 2 drafts are compliant
    regardless of their hand-written body.
    """
    privacy_url = f"{cfg['public_url']}/privacy"
    optout = cfg["from_email"]
    if cold:
        return (
            "\n\n—\n"
            "Ti scrivo a questo indirizzo professionale perché risulti tra i referenti "
            "della tua organizzazione su fonti pubbliche e professionali. Tratto i tuoi "
            "dati di contatto per legittimo interesse al marketing diretto B2B "
            f"(GDPR Art. 6.1.f). Informativa e diritto di opposizione (Art. 21): {privacy_url} "
            f"— oppure rispondi STOP o scrivi a {optout}."
        )
    return (
        "\n\n—\n"
        f"Per non ricevere più questi messaggi rispondi STOP o scrivi a {optout}. "
        f"Informativa: {privacy_url}"
    )


def send_outreach_email(
    *,
    to_email: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
    icp_hypothesis: str,
    lead_id: str,
    idempotency_key: str | None = None,
    in_reply_to: str | None = None,
) -> tuple[bool, str | None]:
    """Outbound Wave 2 cold/follow-up email.

    Adds tracking tags so Resend webhooks can attribute open/click events
    back to the right hypothesis + lead in `outreach_events`.

    Pass `in_reply_to` for follow-up emails to keep the same Gmail thread.

    GDPR: a compliance footer (Art. 14 disclosure on cold, opt-out on follow-up)
    and a List-Unsubscribe header are injected centrally here, so every send is
    lawful even if the draft body omits them. Idempotent: the footer is skipped
    when the caller's body already links to /privacy.
    """
    cfg = _get_config()
    cold = in_reply_to is None
    footer = _outreach_compliance_footer(cfg, cold=cold)

    if "/privacy" not in body_text:
        body_text = body_text.rstrip() + footer

    if body_html is None:
        # Plain-text only emails get higher reply rates in B2B IT (less spam-y).
        body_html = f'<pre style="font-family:Arial,sans-serif;font-size:14px;line-height:1.6;white-space:pre-wrap;">{body_text}</pre>'
    elif "/privacy" not in body_html:
        body_html = body_html + "<br/><br/>" + footer.strip().replace("\n", "<br/>")

    headers: dict[str, str] = {
        # RFC 2369 one-click unsubscribe. Opt-out replies are detected by
        # imap_poller and pushed to suppression_list. Lifts deliverability and
        # reinforces the Art. 6.1.f legitimate-interest opt-out.
        "List-Unsubscribe": f"<mailto:{cfg['from_email']}?subject=unsubscribe>",
    }
    if in_reply_to:
        headers["In-Reply-To"] = in_reply_to
        headers["References"] = in_reply_to
    if idempotency_key:
        headers["X-Idempotency-Key"] = idempotency_key

    return _send_via_resend(
        to_email=to_email,
        subject=subject,
        html=body_html,
        text=body_text,
        headers=headers,
        tags=[
            {"name": "campaign", "value": "outreach_wave2"},
            {"name": "hypothesis", "value": icp_hypothesis},
            {"name": "lead_id", "value": lead_id[:64]},
        ],
    )


# ─────────────────────────── Backward compat ───────────────────────────


def smtp_configured() -> bool:
    """Deprecated alias for email_configured(). Kept for old callers."""
    return email_configured()
