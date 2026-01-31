"""
Unit tests for GeminiClient

Tests HTTP client functionality, session management, and retry logic.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.core.gemini_client import GeminiClient
from app.models.account import Account


@pytest.fixture
def account_data():
    """Basic account data for testing"""
    now = datetime.now(timezone.utc)
    return {
        "email": "test@example.com",
        "team_id": "test-team-id",
        "secure_c_ses": "test-secure-c-ses",
        "host_c_oses": "test-host-c-oses",
        "csesidx": "123456",
        "user_agent": "test-user-agent",
        "created_at": now.isoformat(),
    }


@pytest.fixture
def account(account_data):
    """Create test account"""
    return Account(**account_data)


@pytest.fixture
def gemini_client(account):
    """Create GeminiClient instance"""
    return GeminiClient(account)


class TestGeminiClientInit:
    """Test GeminiClient initialization"""

    def test_init_sets_account(self, gemini_client, account):
        """Init should set account"""
        assert gemini_client.account == account

    def test_init_client_none(self, gemini_client):
        """Init should not create HTTP client yet"""
        assert gemini_client._client is None

    def test_constants(self, gemini_client):
        """Test class constants are set"""
        assert gemini_client.BASE_URL == "https://gemini.google.com"
        assert gemini_client.CHAT_API == "/api/chat"
        assert gemini_client.UPLOAD_API == "/api/upload"
        assert gemini_client.TIMEOUT == 30.0
        assert gemini_client.MAX_RETRIES == 3


class TestAsyncContextManager:
    """Test async context manager support"""

    @pytest.mark.asyncio
    async def test_async_context_manager(self, gemini_client):
        """Client should work as async context manager"""
        async with gemini_client as client:
            assert client._client is not None
            assert isinstance(client._client, httpx.AsyncClient)

        # Client should be closed after exit
        assert client._client is None

    @pytest.mark.asyncio
    async def test_multiple_context_entries(self, gemini_client):
        """Client should handle multiple context manager uses"""
        async with gemini_client:
            pass

        async with gemini_client:
            assert gemini_client._client is not None


class TestEnsureClient:
    """Test _ensure_client method"""

    @pytest.mark.asyncio
    async def test_ensure_client_creates_client(self, gemini_client):
        """_ensure_client should create HTTP client"""
        assert gemini_client._client is None

        await gemini_client._ensure_client()

        assert gemini_client._client is not None
        assert isinstance(gemini_client._client, httpx.AsyncClient)

        # Cleanup
        await gemini_client.close()

    @pytest.mark.asyncio
    async def test_ensure_client_idempotent(self, gemini_client):
        """_ensure_client should be idempotent"""
        await gemini_client._ensure_client()
        first_client = gemini_client._client

        await gemini_client._ensure_client()
        second_client = gemini_client._client

        assert first_client is second_client

        # Cleanup
        await gemini_client.close()


class TestClose:
    """Test close method"""

    @pytest.mark.asyncio
    async def test_close_closes_client(self, gemini_client):
        """close should close HTTP client"""
        await gemini_client._ensure_client()
        assert gemini_client._client is not None

        await gemini_client.close()

        assert gemini_client._client is None

    @pytest.mark.asyncio
    async def test_close_when_none(self, gemini_client):
        """close should work when client is None"""
        assert gemini_client._client is None

        await gemini_client.close()

        assert gemini_client._client is None


class TestGetHeaders:
    """Test _get_headers method"""

    def test_get_headers_structure(self, gemini_client):
        """Headers should have correct structure"""
        token = "test-token"
        headers = gemini_client._get_headers(token)

        assert "Content-Type" in headers
        assert "Authorization" in headers
        assert "User-Agent" in headers
        assert "Cookie" in headers

    def test_get_headers_values(self, gemini_client, account):
        """Headers should have correct values"""
        token = "test-token"
        headers = gemini_client._get_headers(token)

        assert headers["Content-Type"] == "application/json"
        assert headers["Authorization"] == f"Bearer {token}"
        assert headers["User-Agent"] == account.user_agent

    def test_get_headers_cookie(self, gemini_client, account):
        """Cookie header should contain account credentials"""
        token = "test-token"
        headers = gemini_client._get_headers(token)

        cookie = headers["Cookie"]
        assert f"__Secure-c_ses={account.secure_c_ses}" in cookie
        assert f"__Host-c_oses={account.host_c_oses}" in cookie
        assert f"csesidx={account.csesidx}" in cookie


class TestSendMessage:
    """Test send_message method"""

    @pytest.mark.asyncio
    async def test_send_message_success(self, gemini_client):
        """Send message should work successfully"""
        # Mock token manager
        mock_token = "test-jwt-token"
        gemini_client.account.token_manager.get_token = AsyncMock(
            return_value=mock_token
        )

        # Mock HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "conversation_id": "conv-123",
            "response": "Test response",
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        gemini_client._client = mock_client

        # Send message
        result = await gemini_client.send_message("Hello")

        # Verify
        assert result["conversation_id"] == "conv-123"
        assert result["response"] == "Test response"

        # Verify API call
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args

        assert call_args[0][0] == "https://gemini.google.com/api/chat"
        assert call_args[1]["json"]["message"] == "Hello"
        assert call_args[1]["headers"]["Authorization"] == f"Bearer {mock_token}"

    @pytest.mark.asyncio
    async def test_send_message_with_conversation_id(self, gemini_client):
        """Send message with conversation_id"""
        gemini_client.account.token_manager.get_token = AsyncMock(
            return_value="token"
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        gemini_client._client = mock_client

        await gemini_client.send_message("Hello", conversation_id="conv-123")

        # Verify conversation_id in payload
        call_args = mock_client.post.call_args
        payload = call_args[1]["json"]

        assert payload["conversation_id"] == "conv-123"

    @pytest.mark.asyncio
    async def test_send_message_with_kwargs(self, gemini_client):
        """Send message with additional kwargs"""
        gemini_client.account.token_manager.get_token = AsyncMock(
            return_value="token"
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        gemini_client._client = mock_client

        await gemini_client.send_message(
            "Hello",
            temperature=0.7,
            max_tokens=1000,
        )

        # Verify kwargs in payload
        call_args = mock_client.post.call_args
        payload = call_args[1]["json"]

        assert payload["temperature"] == 0.7
        assert payload["max_tokens"] == 1000

    @pytest.mark.asyncio
    async def test_send_message_http_error(self, gemini_client):
        """Send message should raise on HTTP error"""
        gemini_client.account.token_manager.get_token = AsyncMock(
            return_value="token"
        )

        # Mock 401 error
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Unauthorized",
            request=MagicMock(),
            response=mock_response,
        )

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        gemini_client._client = mock_client

        with pytest.raises(httpx.HTTPStatusError):
            await gemini_client.send_message("Hello")


class TestUploadFile:
    """Test upload_file method"""

    @pytest.mark.asyncio
    async def test_upload_file_success(self, gemini_client):
        """Upload file should work successfully"""
        gemini_client.account.token_manager.get_token = AsyncMock(
            return_value="token"
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "file_id": "file-123",
            "status": "uploaded",
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        gemini_client._client = mock_client

        # Upload file
        file_data = b"test file content"
        result = await gemini_client.upload_file(
            file_data,
            filename="test.png",
            mime_type="image/png",
        )

        # Verify
        assert result["file_id"] == "file-123"
        assert result["status"] == "uploaded"

        # Verify API call
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args

        assert call_args[0][0] == "https://gemini.google.com/api/upload"
        assert "file" in call_args[1]["files"]
        assert call_args[1]["data"]["team_id"] == gemini_client.account.team_id

    @pytest.mark.asyncio
    async def test_upload_file_removes_content_type(self, gemini_client):
        """Upload should remove Content-Type header for multipart"""
        gemini_client.account.token_manager.get_token = AsyncMock(
            return_value="token"
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"file_id": "123"}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        gemini_client._client = mock_client

        await gemini_client.upload_file(
            b"data",
            filename="test.png",
            mime_type="image/png",
        )

        # Verify Content-Type not in headers
        call_args = mock_client.post.call_args
        headers = call_args[1]["headers"]

        assert "Content-Type" not in headers


class TestSendMessageWithRetry:
    """Test send_message_with_retry method"""

    @pytest.mark.asyncio
    async def test_retry_success_first_attempt(self, gemini_client):
        """Retry should succeed on first attempt"""
        gemini_client.account.token_manager.get_token = AsyncMock(
            return_value="token"
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        gemini_client._client = mock_client

        result = await gemini_client.send_message_with_retry("Hello")

        assert result["status"] == "ok"
        assert mock_client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_500_error(self, gemini_client):
        """Retry should retry on 500 error"""
        gemini_client.account.token_manager.get_token = AsyncMock(
            return_value="token"
        )

        # First 2 attempts fail with 500, third succeeds
        mock_error_response = MagicMock()
        mock_error_response.status_code = 500

        mock_success_response = MagicMock()
        mock_success_response.status_code = 200
        mock_success_response.json.return_value = {"status": "ok"}

        mock_client = AsyncMock()
        mock_client.post.side_effect = [
            MagicMock(
                raise_for_status=MagicMock(
                    side_effect=httpx.HTTPStatusError(
                        "Server error",
                        request=MagicMock(),
                        response=mock_error_response,
                    )
                )
            ),
            MagicMock(
                raise_for_status=MagicMock(
                    side_effect=httpx.HTTPStatusError(
                        "Server error",
                        request=MagicMock(),
                        response=mock_error_response,
                    )
                )
            ),
            mock_success_response,
        ]

        gemini_client._client = mock_client

        result = await gemini_client.send_message_with_retry("Hello")

        assert result["status"] == "ok"
        assert mock_client.post.call_count == 3

    @pytest.mark.asyncio
    async def test_retry_on_429_rate_limit(self, gemini_client):
        """Retry should retry on 429 rate limit"""
        gemini_client.account.token_manager.get_token = AsyncMock(
            return_value="token"
        )

        mock_error_response = MagicMock()
        mock_error_response.status_code = 429

        mock_success_response = MagicMock()
        mock_success_response.status_code = 200
        mock_success_response.json.return_value = {"status": "ok"}

        mock_client = AsyncMock()
        mock_client.post.side_effect = [
            MagicMock(
                raise_for_status=MagicMock(
                    side_effect=httpx.HTTPStatusError(
                        "Rate limit",
                        request=MagicMock(),
                        response=mock_error_response,
                    )
                )
            ),
            mock_success_response,
        ]

        gemini_client._client = mock_client

        result = await gemini_client.send_message_with_retry("Hello")

        assert result["status"] == "ok"
        assert mock_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_no_retry_on_401_error(self, gemini_client):
        """Retry should NOT retry on 401 error"""
        gemini_client.account.token_manager.get_token = AsyncMock(
            return_value="token"
        )

        mock_error_response = MagicMock()
        mock_error_response.status_code = 401

        mock_client = AsyncMock()
        mock_client.post.return_value = MagicMock(
            raise_for_status=MagicMock(
                side_effect=httpx.HTTPStatusError(
                    "Unauthorized",
                    request=MagicMock(),
                    response=mock_error_response,
                )
            )
        )

        gemini_client._client = mock_client

        with pytest.raises(httpx.HTTPStatusError):
            await gemini_client.send_message_with_retry("Hello")

        # Should only try once (no retry)
        assert mock_client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_max_attempts_exceeded(self, gemini_client):
        """Retry should fail after max attempts"""
        gemini_client.account.token_manager.get_token = AsyncMock(
            return_value="token"
        )

        mock_error_response = MagicMock()
        mock_error_response.status_code = 500

        mock_client = AsyncMock()
        mock_client.post.return_value = MagicMock(
            raise_for_status=MagicMock(
                side_effect=httpx.HTTPStatusError(
                    "Server error",
                    request=MagicMock(),
                    response=mock_error_response,
                )
            )
        )

        gemini_client._client = mock_client

        with pytest.raises(httpx.HTTPStatusError):
            await gemini_client.send_message_with_retry("Hello", max_retries=2)

        # Should try 3 times (initial + 2 retries)
        assert mock_client.post.call_count == 3

    @pytest.mark.asyncio
    async def test_retry_on_network_error(self, gemini_client):
        """Retry should retry on network error"""
        gemini_client.account.token_manager.get_token = AsyncMock(
            return_value="token"
        )

        mock_success_response = MagicMock()
        mock_success_response.status_code = 200
        mock_success_response.json.return_value = {"status": "ok"}

        mock_client = AsyncMock()
        mock_client.post.side_effect = [
            httpx.RequestError("Network error", request=MagicMock()),
            mock_success_response,
        ]

        gemini_client._client = mock_client

        result = await gemini_client.send_message_with_retry("Hello")

        assert result["status"] == "ok"
        assert mock_client.post.call_count == 2


class TestGetStatusInfo:
    """Test get_status_info method"""

    def test_status_info_structure(self, gemini_client):
        """Status info should have all required fields"""
        status = gemini_client.get_status_info()

        assert "account_email" in status
        assert "account_team_id" in status
        assert "account_status" in status
        assert "client_initialized" in status
        assert "base_url" in status

    def test_status_info_values(self, gemini_client, account):
        """Status info should have correct values"""
        status = gemini_client.get_status_info()

        assert status["account_email"] == account.email
        assert status["account_team_id"] == account.team_id
        assert status["client_initialized"] is False
        assert status["base_url"] == "https://gemini.google.com"

    @pytest.mark.asyncio
    async def test_status_info_after_init(self, gemini_client):
        """Status should show client initialized"""
        await gemini_client._ensure_client()

        status = gemini_client.get_status_info()

        assert status["client_initialized"] is True

        # Cleanup
        await gemini_client.close()
