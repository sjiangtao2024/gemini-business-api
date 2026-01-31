"""
Gemini Client - HTTP client for Gemini Business API

Handles HTTP requests to Gemini Business API with:
- Session management with account credentials
- Automatic token refresh integration
- Request/response handling
- Error detection and propagation
"""

import logging
from typing import Any, Dict, Optional

import httpx

from app.models.account import Account

logger = logging.getLogger(__name__)


class GeminiClient:
    """
    HTTP Client for Gemini Business API

    Manages HTTP sessions with account credentials and token management
    """

    # Gemini Business API endpoints
    BASE_URL = "https://gemini.google.com"
    CHAT_API = "/api/chat"
    UPLOAD_API = "/api/upload"

    # Request configuration
    TIMEOUT = 30.0  # 30 seconds
    MAX_RETRIES = 3

    def __init__(self, account: Account):
        """
        Initialize Gemini Client

        Args:
            account: Account instance with credentials
        """
        self.account = account
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        """Async context manager entry"""
        await self._ensure_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()

    async def _ensure_client(self) -> None:
        """Ensure HTTP client is initialized"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.TIMEOUT,
                follow_redirects=True,
            )

    async def close(self) -> None:
        """Close HTTP client"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _get_headers(self, token: str) -> Dict[str, str]:
        """
        Build request headers with account credentials

        Args:
            token: JWT token from TokenManager

        Returns:
            dict: Request headers
        """
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": self.account.user_agent,
            "Cookie": (
                f"__Secure-c_ses={self.account.secure_c_ses}; "
                f"__Host-c_oses={self.account.host_c_oses}; "
                f"csesidx={self.account.csesidx}"
            ),
        }

    async def send_message(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Send message to Gemini Business API

        Args:
            message: User message to send
            conversation_id: Optional conversation ID for context
            **kwargs: Additional request parameters

        Returns:
            dict: API response data

        Raises:
            httpx.HTTPStatusError: On HTTP errors
            httpx.RequestError: On network errors
        """
        await self._ensure_client()

        # Get fresh token from account's token manager
        token = await self.account.token_manager.get_token()

        # Build request payload
        payload = {
            "message": message,
            "team_id": self.account.team_id,
        }

        if conversation_id:
            payload["conversation_id"] = conversation_id

        payload.update(kwargs)

        # Send request
        url = f"{self.BASE_URL}{self.CHAT_API}"
        headers = self._get_headers(token)

        logger.debug(
            f"Sending message to Gemini API: {message[:50]}... "
            f"(account: {self.account.email})"
        )

        response = await self._client.post(
            url,
            json=payload,
            headers=headers,
        )

        # Check for errors
        response.raise_for_status()

        # Parse response
        data = response.json()

        logger.debug(
            f"Received response from Gemini API: "
            f"status={response.status_code}, "
            f"conversation_id={data.get('conversation_id', 'N/A')}"
        )

        return data

    async def upload_file(
        self,
        file_data: bytes,
        filename: str,
        mime_type: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Upload file to Gemini Business API

        Args:
            file_data: File content bytes
            filename: File name
            mime_type: MIME type (e.g., 'image/png', 'video/mp4')
            **kwargs: Additional request parameters

        Returns:
            dict: Upload response with file_id

        Raises:
            httpx.HTTPStatusError: On HTTP errors
            httpx.RequestError: On network errors
        """
        await self._ensure_client()

        # Get fresh token
        token = await self.account.token_manager.get_token()

        # Build multipart form data
        files = {
            "file": (filename, file_data, mime_type)
        }

        data = {
            "team_id": self.account.team_id,
        }
        data.update(kwargs)

        # Send upload request
        url = f"{self.BASE_URL}{self.UPLOAD_API}"
        headers = self._get_headers(token)
        # Remove Content-Type header for multipart/form-data (httpx sets it)
        headers.pop("Content-Type", None)

        logger.debug(
            f"Uploading file to Gemini API: {filename} ({mime_type}, "
            f"{len(file_data)} bytes, account: {self.account.email})"
        )

        response = await self._client.post(
            url,
            files=files,
            data=data,
            headers=headers,
        )

        # Check for errors
        response.raise_for_status()

        # Parse response
        result = response.json()

        logger.debug(
            f"File uploaded successfully: file_id={result.get('file_id', 'N/A')}"
        )

        return result

    async def send_message_with_retry(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        max_retries: Optional[int] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Send message with automatic retry on transient errors

        Args:
            message: User message to send
            conversation_id: Optional conversation ID
            max_retries: Max retry attempts (default: MAX_RETRIES)
            **kwargs: Additional request parameters

        Returns:
            dict: API response data

        Raises:
            httpx.HTTPStatusError: On persistent HTTP errors
            httpx.RequestError: On persistent network errors
        """
        if max_retries is None:
            max_retries = self.MAX_RETRIES

        last_error = None

        for attempt in range(max_retries + 1):
            try:
                return await self.send_message(
                    message,
                    conversation_id=conversation_id,
                    **kwargs
                )
            except httpx.HTTPStatusError as e:
                # Don't retry on client errors (4xx except 429)
                if 400 <= e.response.status_code < 500 and e.response.status_code != 429:
                    raise

                last_error = e

                if attempt < max_retries:
                    logger.warning(
                        f"Request failed (attempt {attempt + 1}/{max_retries + 1}): "
                        f"status={e.response.status_code}, retrying..."
                    )

            except httpx.RequestError as e:
                last_error = e

                if attempt < max_retries:
                    logger.warning(
                        f"Network error (attempt {attempt + 1}/{max_retries + 1}): "
                        f"{type(e).__name__}, retrying..."
                    )

        # All retries failed
        logger.error(f"Request failed after {max_retries + 1} attempts")
        raise last_error

    def get_status_info(self) -> Dict[str, Any]:
        """
        Get client status information

        Returns:
            dict: Client status
        """
        return {
            "account_email": self.account.email,
            "account_team_id": self.account.team_id,
            "account_status": self.account.status.value,
            "client_initialized": self._client is not None,
            "base_url": self.BASE_URL,
        }
