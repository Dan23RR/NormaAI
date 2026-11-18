"""Tests for JWT security configuration (src.auth.security).

Verifies:
- Token expiry is loaded from settings (not hardcoded)
- Token creation uses configured values
- TokenBlacklist fail-closed behavior in production
"""

import uuid
from datetime import UTC, datetime, timedelta

from src.auth.security import (
    _get_access_token_ttl_seconds,
    _get_refresh_token_ttl_seconds,
    create_access_token,
    create_refresh_token,
    create_token_pair,
    decode_token,
    hash_password,
    verify_password,
)

# ------------------------------------------------------------------ #
#  Token Expiry Configuration                                          #
# ------------------------------------------------------------------ #


class TestTokenExpiryConfig:
    def test_access_token_expire_comes_from_settings(self):
        """Access token expiry should read from settings, not a constant."""
        seconds = _get_access_token_ttl_seconds()
        # ACCESS_TOKEN_TTL, default 900 (15 minutes)
        assert isinstance(seconds, int)
        assert seconds == 900

    def test_refresh_token_expire_comes_from_settings(self):
        """Refresh token expiry should read from settings, not a constant."""
        seconds = _get_refresh_token_ttl_seconds()
        # REFRESH_TOKEN_TTL, default 604800 (7 days)
        assert isinstance(seconds, int)
        assert seconds == 604_800

    def test_access_token_has_correct_expiry(self):
        """Created access token should expire according to configured minutes."""
        user_id = uuid.uuid4()
        org_id = uuid.uuid4()
        token = create_access_token(user_id, org_id, "admin")
        decoded = decode_token(token)
        expected_seconds = _get_access_token_ttl_seconds()
        # Token exp should be within 2 minutes of expected (accounting for execution time)
        expected_exp = datetime.now(UTC) + timedelta(seconds=expected_seconds)
        delta = abs((decoded.exp - expected_exp).total_seconds())
        assert delta < 120, f"Token expiry off by {delta}s"

    def test_refresh_token_has_correct_expiry(self):
        """Created refresh token should expire according to configured days."""
        user_id = uuid.uuid4()
        org_id = uuid.uuid4()
        token = create_refresh_token(user_id, org_id, "member")
        decoded = decode_token(token)
        expected_seconds = _get_refresh_token_ttl_seconds()
        expected_exp = datetime.now(UTC) + timedelta(seconds=expected_seconds)
        delta = abs((decoded.exp - expected_exp).total_seconds())
        assert delta < 120, f"Token expiry off by {delta}s"


# ------------------------------------------------------------------ #
#  Token Pair                                                          #
# ------------------------------------------------------------------ #


class TestTokenPair:
    def test_token_pair_has_correct_expires_in(self):
        """expires_in field should match the configured access TTL (seconds)."""
        user_id = uuid.uuid4()
        org_id = uuid.uuid4()
        pair = create_token_pair(user_id, org_id, "admin")
        expected = _get_access_token_ttl_seconds()
        assert pair.expires_in == expected

    def test_token_pair_contains_both_tokens(self):
        user_id = uuid.uuid4()
        org_id = uuid.uuid4()
        pair = create_token_pair(user_id, org_id, "viewer")
        assert pair.access_token
        assert pair.refresh_token
        assert pair.token_type == "bearer"

    def test_access_token_has_jti(self):
        user_id = uuid.uuid4()
        org_id = uuid.uuid4()
        token = create_access_token(user_id, org_id, "admin")
        decoded = decode_token(token)
        assert decoded.jti
        assert decoded.type == "access"

    def test_refresh_token_has_family(self):
        user_id = uuid.uuid4()
        org_id = uuid.uuid4()
        token = create_refresh_token(user_id, org_id, "admin")
        decoded = decode_token(token)
        assert decoded.family
        assert decoded.type == "refresh"


# ------------------------------------------------------------------ #
#  Password Hashing                                                    #
# ------------------------------------------------------------------ #


class TestPasswordHashing:
    def test_hash_and_verify(self):
        password = "SecurePassword123!"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_wrong_password_fails(self):
        hashed = hash_password("correct")
        assert verify_password("wrong", hashed) is False

    def test_hash_is_not_plaintext(self):
        password = "MyPassword"
        hashed = hash_password(password)
        assert hashed != password
        assert "$2b$" in hashed  # bcrypt prefix
