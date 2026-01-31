"""
Unit tests for Chat Routes

Tests API endpoints for chat and file upload functionality.
"""

from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, UploadFile
from httpx import AsyncClient

from app.core.account_pool import AccountPool
from app.models.account import Account
from app.routes.chat import (
    ChatRequest,
    ChatResponse,
    router,
    send_message,
    set_account_pool,
    upload_file,
)


@pytest.fixture
def account_data():
    """Basic account data"""
    now = datetime.now(timezone.utc)
    return {
        "email": "test@example.com",
        "team_id": "test-team-id",
        "secure_c_ses": "test-ses",
        "host_c_oses": "test-oses",
        "csesidx": "123456",
        "user_agent": "test-ua",
        "created_at": now.isoformat(),
    }


@pytest.fixture
def mock_account(account_data):
    """Create mock account"""
    return Account(**account_data)


@pytest.fixture
def mock_pool(mock_account):
    """Create mock account pool"""
    pool = MagicMock(spec=AccountPool)
    pool.get_available_account = AsyncMock(return_value=mock_account)
    pool.handle_error = MagicMock()
    return pool


@pytest.fixture
def setup_pool(mock_pool):
    """Setup account pool for routes"""
    set_account_pool(mock_pool)
    yield
    set_account_pool(None)


class TestChatRequest:
    """Test ChatRequest model"""

    def test_valid_request(self):
        """Valid request should validate"""
        request = ChatRequest(
            message="Hello",
            conversation_id="conv-123",
            temperature=0.7,
        )

        assert request.message == "Hello"
        assert request.conversation_id == "conv-123"
        assert request.temperature == 0.7

    def test_message_required(self):
        """Message field is required"""
        with pytest.raises(ValueError):
            ChatRequest()

    def test_message_min_length(self):
        """Message must be at least 1 character"""
        with pytest.raises(ValueError):
            ChatRequest(message="")

    def test_optional_fields(self):
        """Optional fields should default to None"""
        request = ChatRequest(message="Hello")

        assert request.conversation_id is None
        assert request.temperature is None
        assert request.max_tokens is None


class TestSendMessage:
    """Test send_message endpoint"""

    @pytest.mark.asyncio
    async def test_send_message_success(self, setup_pool, mock_account):
        """Send message successfully"""
        request = ChatRequest(message="Hello")

        # Mock GeminiClient
        with patch("app.routes.chat.GeminiClient") as MockClient:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client.send_message_with_retry = AsyncMock(
                return_value={
                    "response": "Hi there!",
                    "conversation_id": "conv-123",
                }
            )
            MockClient.return_value = mock_client

            response = await send_message(request)

            assert response.response == "Hi there!"
            assert response.conversation_id == "conv-123"
            assert response.account_email == mock_account.email

    @pytest.mark.asyncio
    async def test_send_message_with_optional_params(self, setup_pool):
        """Send message with temperature and max_tokens"""
        request = ChatRequest(
            message="Hello",
            temperature=0.9,
            max_tokens=1000,
        )

        with patch("app.routes.chat.GeminiClient") as MockClient:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client.send_message_with_retry = AsyncMock(
                return_value={
                    "response": "Response",
                    "conversation_id": "conv-123",
                }
            )
            MockClient.return_value = mock_client

            await send_message(request)

            # Verify kwargs passed to client
            call_kwargs = mock_client.send_message_with_retry.call_args[1]
            assert call_kwargs["temperature"] == 0.9
            assert call_kwargs["max_tokens"] == 1000

    @pytest.mark.asyncio
    async def test_send_message_no_pool(self):
        """Send message should fail if pool not initialized"""
        set_account_pool(None)

        request = ChatRequest(message="Hello")

        with pytest.raises(HTTPException) as exc_info:
            await send_message(request)

        assert exc_info.value.status_code == 503
        assert "not initialized" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_send_message_no_available_account(self, mock_pool):
        """Send message should fail if no accounts available"""
        set_account_pool(mock_pool)
        mock_pool.get_available_account.side_effect = Exception("No accounts")

        request = ChatRequest(message="Hello")

        with pytest.raises(HTTPException) as exc_info:
            await send_message(request)

        assert exc_info.value.status_code == 503
        assert "No available accounts" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_send_message_401_error(self, setup_pool, mock_pool):
        """Send message should handle 401 error"""
        import httpx

        request = ChatRequest(message="Hello")

        # Mock 401 error with proper httpx structure
        mock_response = MagicMock()
        mock_response.status_code = 401

        error = httpx.HTTPStatusError(
            "Unauthorized",
            request=MagicMock(),
            response=mock_response,
        )

        with patch("app.routes.chat.GeminiClient") as MockClient:
            # Create async context manager that raises error
            async def mock_aenter(self):
                return self

            async def mock_aexit(self, exc_type, exc_val, exc_tb):
                return False  # Don't suppress exception

            mock_client = MagicMock()
            mock_client.__aenter__ = mock_aenter
            mock_client.__aexit__ = mock_aexit
            mock_client.send_message_with_retry = AsyncMock(side_effect=error)
            MockClient.return_value = mock_client

            with pytest.raises(HTTPException) as exc_info:
                await send_message(request)

            assert exc_info.value.status_code == 401
            assert "Authentication failed" in exc_info.value.detail

            # Verify error handling was called
            mock_pool.handle_error.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_message_429_error(self, setup_pool, mock_pool):
        """Send message should handle 429 rate limit"""
        import httpx

        request = ChatRequest(message="Hello")

        mock_response = MagicMock()
        mock_response.status_code = 429

        error = httpx.HTTPStatusError(
            "Rate limit",
            request=MagicMock(),
            response=mock_response,
        )

        with patch("app.routes.chat.GeminiClient") as MockClient:
            # Create async context manager that raises error
            async def mock_aenter(self):
                return self

            async def mock_aexit(self, exc_type, exc_val, exc_tb):
                return False

            mock_client = MagicMock()
            mock_client.__aenter__ = mock_aenter
            mock_client.__aexit__ = mock_aexit
            mock_client.send_message_with_retry = AsyncMock(side_effect=error)
            MockClient.return_value = mock_client

            with pytest.raises(HTTPException) as exc_info:
                await send_message(request)

            assert exc_info.value.status_code == 429
            assert "Rate limit" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_send_message_network_error(self, setup_pool):
        """Send message should handle network error"""
        request = ChatRequest(message="Hello")

        # Use a generic exception without response attribute
        error = RuntimeError("Network error")

        with patch("app.routes.chat.GeminiClient") as MockClient:
            # Create async context manager that raises error
            async def mock_aenter(self):
                return self

            async def mock_aexit(self, exc_type, exc_val, exc_tb):
                return False

            mock_client = MagicMock()
            mock_client.__aenter__ = mock_aenter
            mock_client.__aexit__ = mock_aexit
            mock_client.send_message_with_retry = AsyncMock(side_effect=error)
            MockClient.return_value = mock_client

            with pytest.raises(HTTPException) as exc_info:
                await send_message(request)

            assert exc_info.value.status_code == 500
            assert "Internal server error" in exc_info.value.detail


class TestUploadFile:
    """Test upload_file endpoint"""

    @pytest.mark.asyncio
    async def test_upload_file_success(self, setup_pool, mock_account):
        """Upload file successfully"""
        # Create mock file
        file_data = b"fake image data"
        mock_file = MagicMock(spec=UploadFile)
        mock_file.filename = "test.png"
        mock_file.content_type = "image/png"
        mock_file.read = AsyncMock(return_value=file_data)

        with patch("app.routes.chat.GeminiClient") as MockClient:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client.upload_file = AsyncMock(
                return_value={"file_id": "file-123"}
            )
            MockClient.return_value = mock_client

            response = await upload_file(mock_file)

            assert response.file_id == "file-123"
            assert response.filename == "test.png"
            assert response.mime_type == "image/png"
            assert response.account_email == mock_account.email

    @pytest.mark.asyncio
    async def test_upload_file_no_pool(self):
        """Upload should fail if pool not initialized"""
        set_account_pool(None)

        mock_file = MagicMock(spec=UploadFile)
        mock_file.content_type = "image/png"

        with pytest.raises(HTTPException) as exc_info:
            await upload_file(mock_file)

        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_upload_file_invalid_type(self, setup_pool):
        """Upload should reject invalid file types"""
        mock_file = MagicMock(spec=UploadFile)
        mock_file.content_type = "application/pdf"

        with pytest.raises(HTTPException) as exc_info:
            await upload_file(mock_file)

        assert exc_info.value.status_code == 400
        assert "Unsupported file type" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_upload_file_too_large(self, setup_pool):
        """Upload should reject files over 20MB"""
        mock_file = MagicMock(spec=UploadFile)
        mock_file.filename = "large.png"
        mock_file.content_type = "image/png"
        # Create 21MB file
        large_data = b"x" * (21 * 1024 * 1024)
        mock_file.read = AsyncMock(return_value=large_data)

        with pytest.raises(HTTPException) as exc_info:
            await upload_file(mock_file)

        assert exc_info.value.status_code == 400
        assert "File too large" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_upload_file_read_error(self, setup_pool):
        """Upload should handle file read errors"""
        mock_file = MagicMock(spec=UploadFile)
        mock_file.content_type = "image/png"
        mock_file.read = AsyncMock(side_effect=Exception("Read error"))

        with pytest.raises(HTTPException) as exc_info:
            await upload_file(mock_file)

        assert exc_info.value.status_code == 400
        assert "Failed to read file" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_upload_file_supported_types(self, setup_pool, mock_account):
        """Test all supported file types"""
        supported_types = [
            "image/png",
            "image/jpeg",
            "image/gif",
            "image/webp",
            "video/mp4",
            "video/quicktime",
            "video/x-msvideo",
        ]

        for mime_type in supported_types:
            mock_file = MagicMock(spec=UploadFile)
            mock_file.filename = f"test.{mime_type.split('/')[-1]}"
            mock_file.content_type = mime_type
            mock_file.read = AsyncMock(return_value=b"data")

            with patch("app.routes.chat.GeminiClient") as MockClient:
                mock_client = MagicMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client.upload_file = AsyncMock(
                    return_value={"file_id": "file-123"}
                )
                MockClient.return_value = mock_client

                response = await upload_file(mock_file)
                assert response.mime_type == mime_type
