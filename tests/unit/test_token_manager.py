"""
Unit tests for Token Manager

Tests the local JWT generation and auto-refresh logic.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.token_manager import TokenManager


@pytest.fixture
def token_manager():
    """Create a TokenManager instance for testing"""
    return TokenManager(
        team_id="test-team-id",
        secure_c_ses="test-secure-c-ses",
        csesidx="test-csesidx",
        user_agent="test-user-agent",
    )


@pytest.fixture
def mock_xsrf_response():
    """Mock response from /auth/getoxsrf endpoint"""
    return {"xsrfToken": "dGVzdC1rZXk=", "keyId": "test-key-id"}  # base64: "test-key"


class TestTokenManagerInit:
    """Test TokenManager initialization"""

    def test_init_sets_credentials(self, token_manager):
        """Test that initialization sets all credentials correctly"""
        assert token_manager.team_id == "test-team-id"
        assert token_manager.secure_c_ses == "test-secure-c-ses"
        assert token_manager.csesidx == "test-csesidx"
        assert token_manager.user_agent == "test-user-agent"

    def test_init_sets_default_state(self, token_manager):
        """Test that initialization sets default token state"""
        assert token_manager.jwt_token is None
        assert token_manager.token_expires_at == 0
        assert token_manager.xsrf_token is None
        assert token_manager.key_id is None

    def test_init_creates_lock(self, token_manager):
        """Test that initialization creates asyncio Lock"""
        assert isinstance(token_manager._refresh_lock, asyncio.Lock)


class TestShouldRefresh:
    """Test _should_refresh logic"""

    def test_should_refresh_when_no_token(self, token_manager):
        """Should refresh when jwt_token is None"""
        assert token_manager._should_refresh() is True

    def test_should_refresh_when_expired(self, token_manager):
        """Should refresh when token is expired"""
        token_manager.jwt_token = "test-token"
        token_manager.token_expires_at = time.time() - 100  # Expired 100 seconds ago
        assert token_manager._should_refresh() is True

    def test_should_refresh_near_expiry(self, token_manager):
        """Should refresh 30 seconds before expiry"""
        token_manager.jwt_token = "test-token"
        # Expires in 20 seconds (less than 30 second threshold)
        token_manager.token_expires_at = time.time() + 20
        assert token_manager._should_refresh() is True

    def test_should_not_refresh_when_valid(self, token_manager):
        """Should not refresh when token is valid and not near expiry"""
        token_manager.jwt_token = "test-token"
        # Expires in 100 seconds (more than 30 second threshold)
        token_manager.token_expires_at = time.time() + 100
        assert token_manager._should_refresh() is False


class TestIsTokenValid:
    """Test is_token_valid method"""

    def test_is_valid_when_no_token(self, token_manager):
        """Token is invalid when jwt_token is None"""
        assert token_manager.is_token_valid() is False

    def test_is_valid_when_expired(self, token_manager):
        """Token is invalid when expired"""
        token_manager.jwt_token = "test-token"
        token_manager.token_expires_at = time.time() - 10
        assert token_manager.is_token_valid() is False

    def test_is_valid_when_not_expired(self, token_manager):
        """Token is valid when not expired"""
        token_manager.jwt_token = "test-token"
        token_manager.token_expires_at = time.time() + 100
        assert token_manager.is_token_valid() is True


class TestGenerateJWT:
    """Test _generate_jwt method"""

    def test_generate_jwt_success(self, token_manager):
        """Successfully generate JWT with valid xsrf_token"""
        token_manager.xsrf_token = "dGVzdC1rZXk="  # base64: "test-key"

        jwt = token_manager._generate_jwt()

        # JWT should have 3 parts: header.payload.signature
        parts = jwt.split(".")
        assert len(parts) == 3

        # Each part should be non-empty
        assert all(len(part) > 0 for part in parts)

    def test_generate_jwt_raises_without_xsrf_token(self, token_manager):
        """Raise exception when xsrf_token is not available"""
        token_manager.xsrf_token = None

        with pytest.raises(Exception, match="xsrf_token not available"):
            token_manager._generate_jwt()


class TestRefreshToken:
    """Test _refresh_token method"""

    @pytest.mark.asyncio
    async def test_refresh_token_success(self, token_manager, mock_xsrf_response):
        """Successfully refresh token with valid response"""
        # Mock httpx.AsyncClient
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_xsrf_response

            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            # Execute refresh
            await token_manager._refresh_token()

            # Verify token state
            assert token_manager.xsrf_token == "dGVzdC1rZXk="
            assert token_manager.key_id == "test-key-id"
            assert token_manager.jwt_token is not None
            assert token_manager.token_expires_at > time.time()

    @pytest.mark.asyncio
    async def test_refresh_token_handles_401(self, token_manager):
        """Handle 401 error from /auth/getoxsrf"""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 401

            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            with pytest.raises(Exception, match="Failed to get xsrfToken"):
                await token_manager._refresh_token()

            # Token state should be reset
            assert token_manager.jwt_token is None
            assert token_manager.token_expires_at == 0

    @pytest.mark.asyncio
    async def test_refresh_token_handles_missing_xsrf(self, token_manager):
        """Handle missing xsrfToken in response"""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {}  # Empty response

            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            with pytest.raises(Exception, match="xsrfToken not found"):
                await token_manager._refresh_token()


class TestGetToken:
    """Test get_token method (main public API)"""

    @pytest.mark.asyncio
    async def test_get_token_first_time(self, token_manager, mock_xsrf_response):
        """Get token for the first time (triggers refresh)"""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_xsrf_response

            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            token = await token_manager.get_token()

            assert token is not None
            assert len(token.split(".")) == 3  # Valid JWT format

    @pytest.mark.asyncio
    async def test_get_token_reuses_valid_token(self, token_manager):
        """Reuse existing token when still valid"""
        # Set up valid token state
        token_manager.jwt_token = "existing-token"
        token_manager.token_expires_at = time.time() + 100

        # Should not trigger refresh
        with patch.object(token_manager, "_refresh_token") as mock_refresh:
            token = await token_manager.get_token()

            assert token == "existing-token"
            mock_refresh.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_token_refreshes_near_expiry(
        self, token_manager, mock_xsrf_response
    ):
        """Refresh token when near expiry (< 30 seconds)"""
        # Set up token near expiry
        token_manager.jwt_token = "old-token"
        token_manager.token_expires_at = time.time() + 20  # 20 seconds left

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_xsrf_response

            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            token = await token_manager.get_token()

            # Should have refreshed (new token)
            assert token != "old-token"

    @pytest.mark.asyncio
    async def test_get_token_concurrent_safety(
        self, token_manager, mock_xsrf_response
    ):
        """Test concurrent calls don't trigger multiple refreshes"""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_xsrf_response

            mock_get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.get = mock_get

            # Make 5 concurrent calls
            results = await asyncio.gather(
                *[token_manager.get_token() for _ in range(5)]
            )

            # All should return the same token
            assert len(set(results)) == 1

            # Should only refresh once (protected by lock)
            assert mock_get.call_count == 1


class TestGetStatus:
    """Test get_status method"""

    def test_get_status_no_token(self, token_manager):
        """Status when no token exists"""
        status = token_manager.get_status()

        assert status["has_token"] is False
        assert status["is_valid"] is False
        assert status["expires_in"] == 0

    def test_get_status_with_valid_token(self, token_manager):
        """Status when token is valid"""
        token_manager.jwt_token = "test-token"
        token_manager.token_expires_at = time.time() + 150

        status = token_manager.get_status()

        assert status["has_token"] is True
        assert status["is_valid"] is True
        assert 140 < status["expires_in"] <= 150  # Approximate check
        assert status["team_id"] == "test-team-id"

    def test_get_status_with_expired_token(self, token_manager):
        """Status when token is expired"""
        token_manager.jwt_token = "test-token"
        token_manager.token_expires_at = time.time() - 10

        status = token_manager.get_status()

        assert status["has_token"] is True
        assert status["is_valid"] is False
        assert status["expires_in"] == 0


class TestBase64URLEncode:
    """Test _base64url_encode static method"""

    def test_base64url_encode(self):
        """Test base64url encoding without padding"""
        result = TokenManager._base64url_encode(b"test")

        # Should be base64url encoded without padding
        assert result == "dGVzdA"  # No trailing '='
        assert "=" not in result
