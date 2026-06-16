"""Tests for JWT authentication system."""

import uuid
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.auth.security import (
    create_access_token,
    create_refresh_token,
    create_token_pair,
    decode_token,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_and_verify(self):
        password = "secure-password-123"
        hashed = hash_password(password)
        assert verify_password(password, hashed)

    def test_wrong_password_fails(self):
        hashed = hash_password("correct-password")
        assert not verify_password("wrong-password", hashed)

    def test_hash_is_unique(self):
        h1 = hash_password("same-password")
        h2 = hash_password("same-password")
        assert h1 != h2  # bcrypt uses random salt


class TestTokenCreation:
    def test_create_access_token(self):
        user_id = uuid.uuid4()
        org_id = uuid.uuid4()
        token = create_access_token(user_id, org_id, "admin")
        assert isinstance(token, str)
        assert len(token) > 50

    def test_decode_access_token(self):
        user_id = uuid.uuid4()
        org_id = uuid.uuid4()
        token = create_access_token(user_id, org_id, "member")
        payload = decode_token(token)
        assert payload.sub == str(user_id)
        assert payload.org_id == str(org_id)
        assert payload.role == "member"
        assert payload.type == "access"

    def test_create_refresh_token(self):
        user_id = uuid.uuid4()
        org_id = uuid.uuid4()
        token = create_refresh_token(user_id, org_id, "admin")
        payload = decode_token(token)
        assert payload.type == "refresh"

    def test_token_pair(self):
        pair = create_token_pair(uuid.uuid4(), uuid.uuid4(), "admin")
        assert pair.access_token
        assert pair.refresh_token
        assert pair.token_type == "bearer"
        assert pair.expires_in == 3600

    def test_expired_token_fails(self):
        token = create_access_token(
            uuid.uuid4(),
            uuid.uuid4(),
            "admin",
            expires_delta=timedelta(seconds=-10),
        )
        with pytest.raises(ValueError, match="Invalid token"):
            decode_token(token)

    def test_invalid_token_fails(self):
        with pytest.raises(ValueError, match="Invalid token"):
            decode_token("not-a-valid-jwt-token")


class TestHS256BlockedInProduction:
    """Verify that HS256 fallback is blocked when APP_ENV=production."""

    def test_hs256_blocked_in_production(self):
        """_load_rsa_keys must call sys.exit(1) in production if RSA keys are missing."""
        from src.auth import security

        mock_settings = MagicMock()
        mock_settings.jwt_private_key = None
        mock_settings.jwt_public_key = None
        mock_settings.jwt_private_key_path = None
        mock_settings.jwt_public_key_path = None
        mock_settings.app_env = "production"

        with patch.object(security, "get_settings", return_value=mock_settings):
            with pytest.raises(SystemExit) as exc_info:
                security._load_rsa_keys()
            assert exc_info.value.code == 1

    def test_hs256_allowed_in_development(self):
        """_load_rsa_keys should fallback to HS256 in non-production environments."""
        from src.auth import security

        mock_settings = MagicMock()
        mock_settings.jwt_private_key = None
        mock_settings.jwt_public_key = None
        mock_settings.jwt_private_key_path = None
        mock_settings.jwt_public_key_path = None
        mock_settings.app_env = "development"
        mock_settings.app_secret_key = "dev-secret-key"

        with patch.object(security, "get_settings", return_value=mock_settings):
            security._load_rsa_keys()
            assert security._algorithm == "HS256"


class TestTokenBlacklistFailClosed:
    """Verify that token blacklist fails closed in production."""

    @pytest.mark.asyncio
    async def test_blacklist_fails_closed_in_production(self):
        """If Redis is unavailable in production, is_blacklisted() returns True."""
        from src.auth.security import TokenBlacklist

        bl = TokenBlacklist()
        # Don't connect to Redis — simulate unavailability
        bl._available = False
        bl._client = None

        with patch("src.auth.security.get_settings") as mock_gs:
            mock_gs.return_value = MagicMock(app_env="production")
            result = await bl.is_blacklisted("some-jti")
            assert result is True

    @pytest.mark.asyncio
    async def test_blacklist_fails_open_in_development(self):
        """If Redis is unavailable in development, is_blacklisted() returns False."""
        from src.auth.security import TokenBlacklist

        bl = TokenBlacklist()
        bl._available = False
        bl._client = None

        with patch("src.auth.security.get_settings") as mock_gs:
            mock_gs.return_value = MagicMock(app_env="development")
            result = await bl.is_blacklisted("some-jti")
            assert result is False


class TestBruteForceProtection:
    """Verify brute-force lockout after MAX_ATTEMPTS failures."""

    @pytest.mark.asyncio
    async def test_lockout_after_max_attempts(self):
        """After 5 failed attempts, check_and_increment returns lockout message."""
        from src.auth.brute_force import MAX_ATTEMPTS, BruteForceProtection

        bf = BruteForceProtection()

        # Mock Redis client
        mock_redis = AsyncMock()
        bf._client = mock_redis
        bf._available = True

        # Simulate attempts under the limit — returns None (allowed)
        mock_redis.get.return_value = "2"  # 2 attempts so far (< MAX_ATTEMPTS)
        mock_redis.pipeline.return_value = AsyncMock()
        result = await bf.check_and_increment("test@example.com", "1.2.3.4")
        assert result is None  # Login allowed

        # Simulate lockout — attempts >= MAX_ATTEMPTS
        mock_redis.get.return_value = str(MAX_ATTEMPTS)
        mock_redis.ttl.return_value = 240  # 4 minutes remaining
        result = await bf.check_and_increment("test@example.com", "1.2.3.4")
        assert result is not None
        assert "Too many failed login attempts" in result
        assert "minute" in result

    @pytest.mark.asyncio
    async def test_reset_clears_attempts(self):
        """Successful login resets the attempt counter."""
        from src.auth.brute_force import BruteForceProtection

        bf = BruteForceProtection()
        mock_redis = AsyncMock()
        bf._client = mock_redis
        bf._available = True

        await bf.reset("test@example.com")
        mock_redis.delete.assert_called_once_with("normaai:bruteforce:test@example.com")

    @pytest.mark.asyncio
    async def test_fails_open_when_redis_unavailable(self):
        """If Redis is unavailable, brute-force check allows login (fail open)."""
        from src.auth.brute_force import BruteForceProtection

        bf = BruteForceProtection()
        bf._client = None
        bf._available = False

        result = await bf.check_and_increment("test@example.com", "1.2.3.4")
        assert result is None  # Allowed — fail open

    @pytest.mark.asyncio
    async def test_remaining_attempts_calculation(self):
        """get_remaining_attempts returns correct count."""
        from src.auth.brute_force import MAX_ATTEMPTS, BruteForceProtection

        bf = BruteForceProtection()
        mock_redis = AsyncMock()
        bf._client = mock_redis
        bf._available = True

        mock_redis.get.return_value = "3"
        remaining = await bf.get_remaining_attempts("test@example.com")
        assert remaining == MAX_ATTEMPTS - 3
