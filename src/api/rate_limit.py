"""Rate limiter singleton.

Extracted from main.py so routers can import the limiter
without importing the entire main module (breaks circular imports).
"""

import logging

from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)


def _rate_limit_key(request) -> str:
    """Rate limit key: user_id from JWT if available, fallback to IP.

    This provides per-user rate limiting for authenticated requests
    and per-IP for unauthenticated ones.
    """
    # Try to extract user_id from already-parsed JWT
    if hasattr(request.state, "user_id"):
        return f"user:{request.state.user_id}"

    # Try to extract from Authorization header without full JWT decode
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            import base64
            import json

            token = auth_header[7:]
            # Decode JWT payload (middle part) without verification
            payload_b64 = token.split(".")[1]
            # Add padding
            payload_b64 += "=" * (4 - len(payload_b64) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            user_id = payload.get("sub")
            if user_id:
                return f"user:{user_id}"
        except Exception:
            pass

    return get_remote_address(request)


limiter = Limiter(key_func=_rate_limit_key)
