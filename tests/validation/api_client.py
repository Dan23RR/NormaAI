"""
NormaAI API Client for Validation Framework.

Handles authentication, request execution, and retry logic
against the real NormaAI backend via HTTP.

Usage:
    client = NormaAIClient(base_url="http://localhost:8000")
    await client.authenticate(email="test@test.com", password="password123")
    result = await client.run_gap_analysis("GDPR", company_profile)
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env from validation directory and project root
_VALIDATION_DIR = Path(__file__).parent
_PROJECT_ROOT = _VALIDATION_DIR.parent.parent
load_dotenv(_VALIDATION_DIR / ".env")
load_dotenv(_PROJECT_ROOT / ".env")


@dataclass
class APIConfig:
    """Configuration for the NormaAI API client."""

    base_url: str = os.getenv("NORMAAI_BASE_URL", "http://localhost:8000")
    api_prefix: str = "/api/v1"

    # Authentication
    auth_email: str = os.getenv("NORMAAI_TEST_EMAIL", "validator@normaai.dev")
    auth_password: str = os.getenv("NORMAAI_TEST_PASSWORD", "NormaAI_Test_2026!")
    auth_name: str = os.getenv("NORMAAI_TEST_NAME", "Validation Runner")
    auth_org: str = os.getenv("NORMAAI_TEST_ORG", "NormaAI Validation")

    # Retry & timeout
    timeout_seconds: int = int(os.getenv("NORMAAI_TIMEOUT", "120"))
    max_retries: int = int(os.getenv("NORMAAI_MAX_RETRIES", "3"))
    retry_delay_base: float = 2.0

    # Rate limiting
    request_delay_ms: int = int(os.getenv("NORMAAI_REQUEST_DELAY_MS", "500"))

    @property
    def api_url(self) -> str:
        return f"{self.base_url}{self.api_prefix}"


@dataclass
class AuthTokens:
    """Stored authentication tokens."""

    access_token: str = ""
    refresh_token: str = ""
    token_type: str = "bearer"
    expires_in: int = 3600
    obtained_at: float = 0.0

    @property
    def is_expired(self) -> bool:
        """Check if access token is likely expired (with 60s buffer)."""
        if not self.access_token:
            return True
        elapsed = time.time() - self.obtained_at
        return elapsed >= (self.expires_in - 60)


class NormaAIClient:
    """
    Async HTTP client for NormaAI API.

    Handles:
    - Registration & login with automatic retry
    - Token refresh when expired
    - Rate limiting between requests
    - Retry logic with exponential backoff
    - Health check before running tests
    """

    def __init__(self, config: APIConfig | None = None):
        self.config = config or APIConfig()
        self.tokens = AuthTokens()
        self._client: httpx.AsyncClient | None = None
        self._last_request_time: float = 0.0
        self._request_count: int = 0
        self._error_count: int = 0

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def connect(self):
        """Initialize the HTTP client."""
        self._client = httpx.AsyncClient(
            base_url=self.config.base_url,
            timeout=httpx.Timeout(self.config.timeout_seconds),
            follow_redirects=True,
            trust_env=False,  # Ignore system proxy settings for direct backend calls
        )

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    # ─── Health Check ─────────────────────────────────────────────

    async def health_check(self) -> dict:
        """
        Check backend health.

        Returns:
            dict with status, qdrant, llm fields

        Raises:
            ConnectionError: If backend is unreachable
        """
        try:
            resp = await self._client.get("/health")
            resp.raise_for_status()
            data = resp.json()
            logger.info(
                f"Health check: status={data.get('status')}, "
                f"qdrant={data.get('qdrant')}, llm={data.get('llm')}"
            )
            return data
        except httpx.ConnectError:
            raise ConnectionError(
                f"Cannot reach NormaAI at {self.config.base_url}. "
                f"Is the backend running? (docker compose up -d)"
            )
        except Exception as e:
            raise ConnectionError(f"Health check failed: {e}")

    async def get_stats(self) -> dict:
        """Get system statistics."""
        resp = await self._client.get(f"{self.config.api_prefix}/stats")
        resp.raise_for_status()
        return resp.json()

    # ─── Authentication ───────────────────────────────────────────

    async def authenticate(
        self,
        email: str | None = None,
        password: str | None = None,
    ) -> bool:
        """
        Authenticate with the backend. Tries login first, then register.

        Args:
            email: Override email from config
            password: Override password from config

        Returns:
            True if authenticated successfully
        """
        email = email or self.config.auth_email
        password = password or self.config.auth_password

        # Try login first
        try:
            tokens = await self._login(email, password)
            self._store_tokens(tokens)
            logger.info(f"Authenticated via login as {email}")
            return True
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise AuthenticationError(
                    "Auth endpoints not found (404). The auth router is not loaded.\n"
                    "Fix: install missing deps in your Python environment:\n"
                    '  pip install "python-jose[cryptography]" "passlib[bcrypt]"\n'
                    "Then restart uvicorn."
                )
            if e.response.status_code == 401:
                logger.info(f"Login failed for {email}, attempting registration...")
            else:
                raise

        # Try registration
        try:
            tokens = await self._register(
                email=email,
                password=password,
                name=self.config.auth_name,
                organization=self.config.auth_org,
            )
            self._store_tokens(tokens)
            logger.info(f"Registered and authenticated as {email}")
            return True
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409:
                # Already registered but wrong password?
                logger.error(f"Email {email} already registered but login failed.")
                raise AuthenticationError(
                    f"Cannot authenticate as {email}. "
                    f"The account exists but the password may be wrong."
                )
            raise

    async def _login(self, email: str, password: str) -> dict:
        """POST /api/v1/auth/login → TokenPair."""
        resp = await self._client.post(
            f"{self.config.api_prefix}/auth/login",
            json={"email": email, "password": password},
        )
        if resp.status_code == 422:
            detail = resp.json().get("detail", resp.text)
            raise AuthenticationError(
                f"Login validation error (422): {detail}\n" f"Email used: {email}"
            )
        resp.raise_for_status()
        return resp.json()

    async def _register(self, email: str, password: str, name: str, organization: str) -> dict:
        """POST /api/v1/auth/register → TokenPair."""
        resp = await self._client.post(
            f"{self.config.api_prefix}/auth/register",
            json={
                "email": email,
                "password": password,
                "name": name,
                "organization_name": organization,
            },
        )
        if resp.status_code == 422:
            detail = resp.json().get("detail", resp.text)
            raise AuthenticationError(
                f"Registration validation error (422): {detail}\n" f"Email used: {email}"
            )
        resp.raise_for_status()
        return resp.json()

    async def _refresh_tokens(self) -> bool:
        """Refresh the access token using the refresh token."""
        if not self.tokens.refresh_token:
            return False

        try:
            resp = await self._client.post(
                f"{self.config.api_prefix}/auth/refresh",
                json={"refresh_token": self.tokens.refresh_token},
            )
            resp.raise_for_status()
            self._store_tokens(resp.json())
            logger.debug("Tokens refreshed successfully")
            return True
        except Exception as e:
            logger.warning(f"Token refresh failed: {e}")
            return False

    def _store_tokens(self, token_data: dict):
        """Store authentication tokens."""
        self.tokens = AuthTokens(
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token", ""),
            token_type=token_data.get("token_type", "bearer"),
            expires_in=token_data.get("expires_in", 3600),
            obtained_at=time.time(),
        )

    def _auth_headers(self) -> dict:
        """Get authorization headers."""
        return {"Authorization": f"Bearer {self.tokens.access_token}"}

    # ─── Core API Calls ───────────────────────────────────────────

    async def run_qa(
        self,
        question: str,
        company_profile: dict,
        language: str = "it",
    ) -> dict:
        """
        POST /api/v1/qa

        Args:
            question: Regulatory question
            company_profile: Company details
            language: Response language (default: Italian)

        Returns:
            Full API response dict
        """
        payload = {
            "question": question,
            "company_profile": company_profile,
            "language": language,
        }
        return await self._api_call("POST", "/qa", payload)

    async def run_gap_analysis(
        self,
        framework: str,
        company_profile: dict,
    ) -> dict:
        """
        POST /api/v1/gap-analysis

        Args:
            framework: Framework enum (GDPR, CSRD, DORA, NIS2, etc.)
            company_profile: Company details

        Returns:
            Full API response dict
        """
        payload = {
            "framework": framework,
            "company_profile": company_profile,
        }
        return await self._api_call("POST", "/gap-analysis", payload)

    async def run_monitor(
        self,
        regulation_change: str,
        company_profile: dict,
    ) -> dict:
        """
        POST /api/v1/monitor

        Args:
            regulation_change: Description of the regulatory change
            company_profile: Company details

        Returns:
            Full API response dict
        """
        payload = {
            "regulation_change": regulation_change,
            "company_profile": company_profile,
        }
        return await self._api_call("POST", "/monitor", payload)

    # ─── Generic API Call with Retry ──────────────────────────────

    async def _api_call(
        self,
        method: str,
        endpoint: str,
        payload: dict | None = None,
    ) -> dict:
        """
        Execute an authenticated API call with retry logic.

        Handles:
        - Token refresh on 401
        - Rate limit backoff on 429
        - Exponential retry on 5xx
        - Request delay for rate limiting
        """
        # Ensure we have a valid token
        if self.tokens.is_expired:
            if not await self._refresh_tokens():
                await self.authenticate()

        url = f"{self.config.api_prefix}{endpoint}"

        for attempt in range(self.config.max_retries + 1):
            # Rate limiting delay
            await self._rate_limit_delay()

            try:
                resp = await self._client.request(
                    method,
                    url,
                    json=payload,
                    headers=self._auth_headers(),
                )
                self._request_count += 1
                self._last_request_time = time.time()

                # Handle specific status codes
                if resp.status_code == 401:
                    # Token expired mid-request, refresh and retry
                    if attempt < self.config.max_retries:
                        logger.info("Got 401, refreshing token...")
                        if await self._refresh_tokens():
                            continue
                        await self.authenticate()
                        continue

                if resp.status_code == 429:
                    # Rate limited - wait and retry
                    retry_after = int(resp.headers.get("Retry-After", "5"))
                    logger.warning(f"Rate limited on {endpoint}, waiting {retry_after}s")
                    await asyncio.sleep(retry_after)
                    continue

                if resp.status_code >= 500:
                    # Server error - exponential backoff
                    delay = self.config.retry_delay_base * (2**attempt)
                    logger.warning(
                        f"Server error {resp.status_code} on {endpoint}, "
                        f"retry {attempt + 1}/{self.config.max_retries} in {delay:.1f}s"
                    )
                    if attempt < self.config.max_retries:
                        await asyncio.sleep(delay)
                        continue

                resp.raise_for_status()
                return resp.json()

            except httpx.TimeoutException:
                self._error_count += 1
                delay = self.config.retry_delay_base * (2**attempt)
                logger.warning(
                    f"Timeout on {endpoint} (attempt {attempt + 1}), " f"retrying in {delay:.1f}s"
                )
                if attempt < self.config.max_retries:
                    await asyncio.sleep(delay)
                    continue
                raise APITimeoutError(
                    f"Request to {endpoint} timed out after "
                    f"{self.config.timeout_seconds}s "
                    f"({self.config.max_retries + 1} attempts)"
                )

            except httpx.ConnectError:
                raise ConnectionError(
                    f"Cannot connect to NormaAI at {self.config.base_url}. "
                    f"Is the backend running?"
                )

        raise APIError(f"Failed after {self.config.max_retries + 1} attempts on {endpoint}")

    async def _rate_limit_delay(self):
        """Enforce minimum delay between requests."""
        if self._last_request_time > 0:
            elapsed_ms = (time.time() - self._last_request_time) * 1000
            required_delay_ms = self.config.request_delay_ms
            if elapsed_ms < required_delay_ms:
                await asyncio.sleep((required_delay_ms - elapsed_ms) / 1000)

    # ─── Statistics ───────────────────────────────────────────────

    @property
    def stats(self) -> dict:
        """Return client statistics."""
        return {
            "total_requests": self._request_count,
            "total_errors": self._error_count,
            "is_authenticated": not self.tokens.is_expired,
        }


# ─── Custom Exceptions ───────────────────────────────────────────


class AuthenticationError(Exception):
    """Raised when authentication fails."""

    pass


class APIError(Exception):
    """Raised when an API call fails after retries."""

    pass


class APITimeoutError(APIError):
    """Raised when an API call times out."""

    pass
