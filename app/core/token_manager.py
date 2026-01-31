"""
Token Manager - Local JWT Generation and Auto-refresh

CRITICAL: JWT is generated LOCALLY using HMAC-SHA256, NOT returned from server!

Refresh Flow:
1. Request signing key from Google: /auth/getoxsrf
2. Server returns: {"xsrfToken": "base64_key", "keyId": "key_id"}
3. Generate JWT locally using HMAC-SHA256
4. JWT validity: 300 seconds (5 minutes)
5. Refresh proactively at 270 seconds (4.5 minutes)
"""

import asyncio
import base64
import hashlib
import hmac
import json
import time
from typing import Optional

import httpx


class TokenManager:
    """Manages JWT token generation and auto-refresh for Gemini Business API"""

    def __init__(
        self,
        team_id: str,
        secure_c_ses: str,
        csesidx: str,
        user_agent: str,
    ):
        """
        Initialize Token Manager

        Args:
            team_id: Gemini Business team ID (also used as config_id)
            secure_c_ses: Cookie __Secure-c-SES
            csesidx: Cookie csesidx
            user_agent: Browser User-Agent
        """
        self.team_id = team_id
        self.secure_c_ses = secure_c_ses
        self.csesidx = csesidx
        self.user_agent = user_agent

        # Token state
        self.jwt_token: Optional[str] = None
        self.token_expires_at: float = 0
        self.xsrf_token: Optional[str] = None
        self.key_id: Optional[str] = None

        # Concurrency protection
        self._refresh_lock = asyncio.Lock()

        # Configuration
        self.token_validity_seconds = 300  # 5 minutes
        self.refresh_before_seconds = 30  # Refresh 30 seconds before expiry
        self.base_url = "https://business.gemini.google"

    async def get_token(self) -> str:
        """
        Get valid JWT token, auto-refresh if expired or near expiry

        Returns:
            str: Valid JWT token

        Raises:
            Exception: If token refresh fails
        """
        async with self._refresh_lock:
            # Check if token needs refresh
            if self._should_refresh():
                await self._refresh_token()

            if not self.jwt_token:
                raise Exception("Failed to obtain JWT token")

            return self.jwt_token

    def _should_refresh(self) -> bool:
        """
        Check if token should be refreshed

        Returns:
            bool: True if token is None, expired, or near expiry
        """
        if not self.jwt_token:
            return True

        # Refresh proactively 30 seconds before expiry
        current_time = time.time()
        refresh_at = self.token_expires_at - self.refresh_before_seconds

        return current_time >= refresh_at

    def is_token_valid(self) -> bool:
        """
        Check if current token is still valid

        Returns:
            bool: True if token exists and not expired
        """
        if not self.jwt_token:
            return False

        current_time = time.time()
        return current_time < self.token_expires_at

    async def _refresh_token(self) -> None:
        """
        Refresh JWT token by requesting signing key and generating JWT locally

        Steps:
        1. Request xsrfToken from /auth/getoxsrf
        2. Generate JWT locally using HMAC-SHA256
        3. Update token_expires_at
        """
        try:
            # Step 1: Request signing key from Google
            url = f"{self.base_url}/auth/getoxsrf"
            params = {"csesidx": self.csesidx}
            headers = {
                "Cookie": f"__Secure-c-SES={self.secure_c_ses}; csesidx={self.csesidx}",
                "User-Agent": self.user_agent,
            }

            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, headers=headers)

                if response.status_code != 200:
                    raise Exception(
                        f"Failed to get xsrfToken: HTTP {response.status_code}"
                    )

                data = response.json()
                self.xsrf_token = data.get("xsrfToken")
                self.key_id = data.get("keyId")

                if not self.xsrf_token:
                    raise Exception("xsrfToken not found in response")

            # Step 2: Generate JWT locally
            self.jwt_token = self._generate_jwt()

            # Step 3: Update expiry time
            self.token_expires_at = time.time() + self.token_validity_seconds

        except Exception as e:
            # Reset token state on failure
            self.jwt_token = None
            self.token_expires_at = 0
            raise Exception(f"Token refresh failed: {e}")

    def _generate_jwt(self) -> str:
        """
        Generate JWT locally using HMAC-SHA256

        Returns:
            str: JWT token in format "header.payload.signature"

        Raises:
            Exception: If xsrf_token is not available
        """
        if not self.xsrf_token:
            raise Exception("xsrf_token not available for JWT generation")

        # Decode signing key
        key_bytes = base64.b64decode(self.xsrf_token)

        # Build JWT header
        header = {"alg": "HS256", "typ": "JWT"}

        # Build JWT payload
        now = int(time.time())
        payload = {
            "iss": "gemini-business",
            "aud": "gemini-business-api",
            "sub": self.team_id,
            "iat": now,
            "exp": now + self.token_validity_seconds,
            "nbf": now,
        }

        # Encode header and payload
        header_b64 = self._base64url_encode(json.dumps(header).encode())
        payload_b64 = self._base64url_encode(json.dumps(payload).encode())

        # Create signature using HMAC-SHA256
        message = f"{header_b64}.{payload_b64}"
        signature = hmac.new(key_bytes, message.encode(), hashlib.sha256).digest()
        signature_b64 = self._base64url_encode(signature)

        # Return complete JWT
        return f"{message}.{signature_b64}"

    @staticmethod
    def _base64url_encode(data: bytes) -> str:
        """
        Base64URL encode (without padding)

        Args:
            data: Bytes to encode

        Returns:
            str: Base64URL encoded string without padding
        """
        return base64.urlsafe_b64encode(data).decode().rstrip("=")

    def get_status(self) -> dict:
        """
        Get token manager status for monitoring

        Returns:
            dict: Status information
        """
        if not self.jwt_token:
            return {
                "has_token": False,
                "is_valid": False,
                "expires_in": 0,
            }

        current_time = time.time()
        expires_in = max(0, int(self.token_expires_at - current_time))

        return {
            "has_token": True,
            "is_valid": self.is_token_valid(),
            "expires_in": expires_in,
            "expires_at": self.token_expires_at,
            "team_id": self.team_id,
        }
