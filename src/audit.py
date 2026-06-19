"""Structured audit logging for security-sensitive operations.

Provides a centralized audit trail with structured JSON output for:
- Authentication events (login, logout, register, token refresh)
- Data access events (queries, document uploads, exports)
- Administrative actions (user management, role changes, config changes)
- Security events (failed auth, rate limiting, suspicious activity)

All audit events include: who, what, when, where (IP), and outcome.
"""

from datetime import UTC, datetime
from enum import Enum

import structlog

# Dedicated audit logger - separate from application logs
# Configure to write to a dedicated file/stream in production
audit_logger = structlog.get_logger("normaai.audit")


class AuditAction(str, Enum):
    """Categories of auditable actions."""

    # Auth
    LOGIN_SUCCESS = "auth.login.success"
    LOGIN_FAILURE = "auth.login.failure"
    LOGOUT = "auth.logout"
    REGISTER = "auth.register"
    TOKEN_REFRESH = "auth.token.refresh"
    TOKEN_REVOKED = "auth.token.revoked"
    TOKEN_REUSE_DETECTED = "auth.token.reuse_detected"

    # Conversations
    CONVERSATION_CREATED = "data.conversation.created"
    CONVERSATION_DELETED = "data.conversation.deleted"

    # Alerts
    ALERT_CREATED = "data.alert.created"
    ALERT_DISMISSED = "data.alert.dismissed"

    # Reports
    REPORT_GENERATED = "data.report.generated"

    # Clients
    CLIENT_CREATED = "data.client.created"
    CLIENT_UPDATED = "data.client.updated"
    CLIENT_DELETED = "data.client.deleted"

    # Data access
    QA_QUERY = "data.qa.query"
    GAP_ANALYSIS = "data.gap_analysis.run"
    MONITOR_CHECK = "data.monitor.check"
    DOCUMENT_UPLOAD = "data.document.upload"
    CRAWL_TRIGGERED = "data.crawl.triggered"
    DATA_EXPORT = "data.export"
    DATA_ERASURE = "data.erasure"  # GDPR Art. 17 right to be forgotten

    # Admin
    USER_CREATED = "admin.user.created"
    USER_DEACTIVATED = "admin.user.deactivated"
    ROLE_CHANGED = "admin.role.changed"
    CONFIG_CHANGED = "admin.config.changed"

    # Security
    RATE_LIMIT_HIT = "security.rate_limit"
    INVALID_TOKEN = "security.invalid_token"
    FORBIDDEN_ACCESS = "security.forbidden"
    SUSPICIOUS_INPUT = "security.suspicious_input"


class AuditOutcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"
    ERROR = "error"


def audit_log(
    action: AuditAction,
    outcome: AuditOutcome = AuditOutcome.SUCCESS,
    user_id: str | None = None,
    org_id: str | None = None,
    ip_address: str | None = None,
    resource: str | None = None,
    detail: str | None = None,
    request_id: str | None = None,
    extra: dict | None = None,
) -> None:
    """Record a structured audit event.

    Args:
        action: The type of action being audited
        outcome: Whether the action succeeded or failed
        user_id: ID of the user performing the action
        org_id: Organization ID context
        ip_address: Client IP address
        resource: The resource being accessed (e.g., endpoint, document)
        detail: Human-readable description of what happened
        request_id: Correlation ID for request tracing
        extra: Additional context-specific data
    """
    event = {
        "audit": True,
        "action": action.value,
        "outcome": outcome.value,
        "timestamp": datetime.now(UTC).isoformat(),
        "user_id": user_id,
        "org_id": org_id,
        "ip_address": ip_address,
        "resource": resource,
        "request_id": request_id,
    }

    if detail:
        event["detail"] = detail
    if extra:
        event.update(extra)

    # Remove None values for cleaner output
    event = {k: v for k, v in event.items() if v is not None}

    # Route to appropriate log level based on outcome
    if outcome == AuditOutcome.SUCCESS:
        audit_logger.info("audit_event", **event)
    elif outcome == AuditOutcome.FAILURE or outcome == AuditOutcome.DENIED:
        audit_logger.warning("audit_event", **event)
    elif outcome == AuditOutcome.ERROR:
        audit_logger.error("audit_event", **event)


def get_client_ip(request) -> str:
    """Extract the client IP, resisting X-Forwarded-For spoofing.

    X-Forwarded-For is a client-appendable header: each proxy appends the IP of
    the host that connected to it, so the LEFTMOST entries are attacker-controlled
    and only the rightmost ``trusted_proxy_count`` entries (added by our own
    proxies) can be trusted. We therefore read the entry appended by the
    OUTERMOST trusted proxy -- index ``-trusted_proxy_count`` from the end --
    rather than the spoofable first one. With no proxy in front
    (``trusted_proxy_count == 0``) the header is ignored entirely and only the
    direct socket peer is used.

    This matters for rate limiting and audit integrity: the old "first entry"
    logic let any client forge their logged/limited IP via a header.
    """
    from src.config import get_settings

    trusted = get_settings().trusted_proxy_count

    if trusted > 0:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            parts = [p.strip() for p in forwarded.split(",") if p.strip()]
            if parts:
                # The real client IP is the one our outermost trusted proxy
                # appended. Clamp if the chain is shorter than expected (a
                # spoofed-short header can only push the index left, never past 0).
                idx = max(0, len(parts) - trusted)
                return parts[idx]

        # X-Real-IP is single-valued (set by nginx); only honor it behind a proxy.
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()

    # No trusted proxy, or no forwarding headers: use the direct socket peer.
    if request.client:
        return request.client.host

    return "unknown"
