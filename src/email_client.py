"""Email client - Resend SDK with graceful fallback.

Free tier: 3000 email/month, 100/day. DKIM auto on verified domains.
Migrated from smtplib (G6.17) for:
  - Proper deliverability (DKIM/SPF/DMARC handled by provider)
  - Open + click tracking webhooks
  - No more sender drift (no more @gmail.com posing as founder)

Env vars (read via src.config.get_settings):
    RESEND_API_KEY         (required for actual sending)
    RESEND_FROM_EMAIL      (default: info@normaai.org)
    RESEND_FROM_NAME       (default: "NormaAI")
    RESEND_REPLY_TO        (default: info@normaai.org)
    NORMAAI_PUBLIC_URL     (used to build absolute URLs)

Exposes three send paths:
    send_codex_email()            - inbound (post-form Codex download)
    send_verification_email()     - account email verification link
    send_document_digest_email()  - "N documenti da rivedere" (document surveillance)

Returns (success, error_message) without raising. Without RESEND_API_KEY every
send is a no-op that logs ``resend_not_configured``.
"""

from __future__ import annotations

import os
from html import escape

import structlog

logger = structlog.get_logger()


# ─────────────────────────── Config ───────────────────────────


def _get_config() -> dict:
    return {
        "api_key": os.environ.get("RESEND_API_KEY", "").strip(),
        "from_email": os.environ.get("RESEND_FROM_EMAIL", "info@normaai.org").strip(),
        "from_name": os.environ.get("RESEND_FROM_NAME", "NormaAI").strip(),
        "reply_to": os.environ.get("RESEND_REPLY_TO", "info@normaai.org").strip(),
        "public_url": os.environ.get("NORMAAI_PUBLIC_URL", "https://normaai.org").rstrip("/"),
    }


def email_configured() -> bool:
    return bool(_get_config()["api_key"])


def _from_header(cfg: dict) -> str:
    return f"{cfg['from_name']} <{cfg['from_email']}>"


# ─────────────────────────── Templates ───────────────────────────


def _codex_email_html(recipient_name: str, download_url: str) -> str:
    """Inbound Codex download - brand-consistent dark template."""
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


def _verification_email_html(recipient_name: str, verify_url: str, ttl_hours: int) -> str:
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
        <h1 style="font-size:22px;color:#e6ebf2;margin:0 0 12px;font-weight:700;">Conferma il tuo indirizzo email.</h1>
        <p style="color:#aab3c0;font-size:14px;line-height:1.5;margin:0 0 16px;">
          Ciao {name}, per attivare il tuo account NormaAI conferma l'indirizzo email con il pulsante qui sotto.
        </p>
        <p style="margin:24px 0 8px;">
          <a href="{verify_url}"
             style="display:inline-block;background:#5b8cff;color:#0a0d12;text-decoration:none;font-weight:600;padding:12px 22px;border-radius:8px;font-size:14px;">
            Conferma email
          </a>
        </p>
        <p style="color:#6f7a8a;font-size:12px;line-height:1.5;margin:16px 0 0;">
          Il link è personale e scade tra {ttl_hours} ore. Se non hai creato un account NormaAI, ignora questa email.
        </p>
      </td></tr>
      <tr><td style="padding:24px 0 0;color:#6f7a8a;font-size:11px;">
        NormaAI · info@normaai.org
      </td></tr>
    </table>
  </td></tr>
</table>
</body></html>
"""


def _verification_email_text(recipient_name: str, verify_url: str, ttl_hours: int) -> str:
    name = recipient_name or "ciao"
    return f"""Ciao {name},

per attivare il tuo account NormaAI conferma l'indirizzo email aprendo questo link
(valido {ttl_hours} ore):
{verify_url}

Se non hai creato un account NormaAI, ignora questa email.

NormaAI · info@normaai.org
"""


def send_verification_email(
    to_email: str,
    recipient_name: str,
    verify_url: str,
    ttl_hours: int = 48,
) -> tuple[bool, str | None]:
    """Account email verification link (registration / resend)."""
    return _send_via_resend(
        to_email=to_email,
        subject="Conferma il tuo indirizzo email - NormaAI",
        html=_verification_email_html(recipient_name, verify_url, ttl_hours),
        text=_verification_email_text(recipient_name, verify_url, ttl_hours),
        tags=[{"name": "campaign", "value": "email_verification"}],
    )


# ─────────────────────────── Document digest ───────────────────────────
# Sent by the scheduled surveillance (src/document_check/surveillance.py) to the
# users of an organisation when provisions cited in its documents changed.


def _digest_title(total: int) -> str:
    return "1 documento da rivedere" if total == 1 else f"{total} documenti da rivedere"


def _digest_opening(recipient_name: str, total: int) -> str:
    greeting = f"Ciao {recipient_name}," if recipient_name else "Ciao,"
    where = "in questo documento" if total == 1 else "in questi documenti"
    return f"{greeting} dopo il controllo sono cambiate disposizioni di legge citate {where}."


def _digest_more(shown: int, total: int) -> str:
    rest = total - shown
    if rest <= 0:
        return ""
    return "E un altro documento." if rest == 1 else f"E altri {rest} documenti."


_DIGEST_NOTE = (
    "Il confronto riguarda il testo ufficiale delle disposizioni: apri il controllo per "
    "vedere che cosa è cambiato. Non è un parere legale."
)
_DIGEST_WHY = (
    "Ricevi questa email perché in NormaAI sono attivi gli avvisi sui documenti controllati "
    "dalla tua organizzazione."
)


def _document_digest_html(
    recipient_name: str,
    documents: list[dict],
    total: int,
    app_url: str,
    unsubscribe_url: str,
    contact: str,
) -> str:
    items = "".join(
        '<li style="margin:0 0 12px;">'
        f'<a href="{escape(str(doc.get("url") or app_url), quote=True)}" '
        f'style="color:#0A3A9C;font-weight:600;">{escape(str(doc.get("filename") or ""))}</a>'
        f'<br><span style="color:#44506A;font-size:14px;">'
        f"{escape('; '.join(str(p) for p in doc.get('provisions') or []))}</span></li>"
        for doc in documents
    )
    more = _digest_more(len(documents), total)
    more_html = f'<p style="font-size:15px;margin:0 0 16px;">{escape(more)}</p>' if more else ""
    return f"""<!doctype html>
<html lang="it"><body style="margin:0;padding:0;background:#ffffff;color:#0C1B33;font-family:'Public Sans',Arial,Helvetica,sans-serif;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#ffffff;">
  <tr><td align="center" style="padding:24px 12px;">
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="600" style="max-width:600px;width:100%;">
      <tr><td style="font-size:16px;font-weight:600;color:#0C1B33;padding:0 0 20px;">NormaAI</td></tr>
      <tr><td>
        <h1 style="font-family:Literata,Georgia,serif;font-size:22px;line-height:1.3;color:#0C1B33;margin:0 0 12px;font-weight:600;">{escape(_digest_title(total))}</h1>
        <p style="font-size:15px;line-height:1.55;margin:0 0 16px;">{escape(_digest_opening(recipient_name, total))}</p>
        <ul style="font-size:15px;line-height:1.5;margin:0 0 16px;padding:0 0 0 20px;">{items}</ul>
        {more_html}
        <p style="margin:20px 0;">
          <a href="{escape(app_url, quote=True)}"
             style="display:inline-block;background:#0A3A9C;color:#ffffff;text-decoration:none;font-weight:600;padding:12px 20px;border-radius:6px;font-size:15px;">
            Apri i controlli
          </a>
        </p>
        <p style="font-size:13px;line-height:1.5;color:#44506A;margin:0 0 20px;">{escape(_DIGEST_NOTE)}</p>
      </td></tr>
      <tr><td style="border-top:1px solid #D9DEE8;padding:16px 0 0;font-size:12px;line-height:1.5;color:#44506A;">
        {escape(_DIGEST_WHY)}
        <a href="{escape(unsubscribe_url, quote=True)}" style="color:#0A3A9C;">Non ricevere più questa email</a>.<br>
        NormaAI, {escape(contact)}
      </td></tr>
    </table>
  </td></tr>
</table>
</body></html>
"""


def _document_digest_text(
    recipient_name: str,
    documents: list[dict],
    total: int,
    app_url: str,
    unsubscribe_url: str,
    contact: str,
) -> str:
    lines = [_digest_opening(recipient_name, total), ""]
    for doc in documents:
        lines.append(f"- {doc.get('filename') or ''}")
        provisions = "; ".join(str(p) for p in doc.get("provisions") or [])
        if provisions:
            lines.append(f"  {provisions}")
        lines.append(f"  {doc.get('url') or app_url}")
    more = _digest_more(len(documents), total)
    if more:
        lines += ["", more]
    lines += [
        "",
        f"Apri i controlli: {app_url}",
        "",
        _DIGEST_NOTE,
        "",
        _DIGEST_WHY,
        f"Per non riceverla più: {unsubscribe_url}",
        "",
        f"NormaAI, {contact}",
        "",
    ]
    return "\n".join(lines)


def send_document_digest_email(
    *,
    to_email: str,
    recipient_name: str,
    documents: list[dict],
    app_url: str,
    unsubscribe_url: str,
    total: int | None = None,
) -> tuple[bool, str | None]:
    """The digest of the document surveillance: "N documenti da rivedere".

    ``documents`` are ``{"filename", "url", "provisions": [...]}``; ``total`` is
    how many there are in all when only the first ones are listed. The message
    carries the ``List-Unsubscribe`` headers (one click, RFC 8058) next to the
    link in its footer.
    """
    count = total if total is not None else len(documents)
    contact = _get_config()["reply_to"]
    return _send_via_resend(
        to_email=to_email,
        subject=f"NormaAI: {_digest_title(count)}",
        html=_document_digest_html(
            recipient_name, documents, count, app_url, unsubscribe_url, contact
        ),
        text=_document_digest_text(
            recipient_name, documents, count, app_url, unsubscribe_url, contact
        ),
        headers={
            "List-Unsubscribe": f"<{unsubscribe_url}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
        tags=[{"name": "campaign", "value": "document_digest"}],
    )


# ─────────────────────────── Backward compat ───────────────────────────


def smtp_configured() -> bool:
    """Deprecated alias for email_configured(). Kept for old callers."""
    return email_configured()
