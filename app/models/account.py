"""
Account Model - Gemini Business Account with 30-day lifecycle

Represents a single Gemini Business account with:
- Cookie credentials
- Token Manager instance
- 30-day trial period tracking
- Cooldown management
- Status tracking
"""

import time
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from app.core.token_manager import TokenManager


class AccountStatus(str, Enum):
    """Account status enumeration"""

    ACTIVE = "active"  # Normal usage
    COOLDOWN_401 = "cooldown_401"  # Auth error cooldown
    COOLDOWN_403 = "cooldown_403"  # Forbidden error cooldown
    COOLDOWN_429 = "cooldown_429"  # Rate limit cooldown
    EXPIRED = "expired"  # 30-day trial ended
    EXPIRING_SOON = "expiring_soon"  # < 3 days remaining
    ERROR = "error"  # Multiple consecutive failures


class Account:
    """
    Gemini Business Account with lifecycle management

    CRITICAL: Accounts have 30-day trial period from creation
    """

    def __init__(
        self,
        email: str,
        team_id: str,
        secure_c_ses: str,
        host_c_oses: str,
        csesidx: str,
        user_agent: str,
        created_at: str,
        expires_at: Optional[str] = None,
    ):
        """
        Initialize Account

        Args:
            email: Registration email
            team_id: Gemini Business team ID (also used as config_id)
            secure_c_ses: Cookie __Secure-c-SES
            host_c_oses: Cookie __Host-c-OSES
            csesidx: Cookie csesidx
            user_agent: Browser User-Agent
            created_at: Account creation timestamp (ISO 8601 format)
            expires_at: Optional explicit expiry time (ISO 8601 format)
        """
        # Basic info
        self.email = email
        self.team_id = team_id
        self.secure_c_ses = secure_c_ses
        self.host_c_oses = host_c_oses
        self.csesidx = csesidx
        self.user_agent = user_agent

        # Parse timestamps
        self.created_at = self._parse_timestamp(created_at)
        self.expires_at = self._parse_timestamp(expires_at) if expires_at else None

        # Token Manager instance (one per account)
        self.token_manager = TokenManager(
            team_id=team_id,
            secure_c_ses=secure_c_ses,
            csesidx=csesidx,
            user_agent=user_agent,
        )

        # Account status
        self.status = AccountStatus.ACTIVE
        self.cooldown_until: float = 0  # Unix timestamp
        self.request_count: int = 0
        self.error_count: int = 0
        self.last_used_at: float = 0

    @staticmethod
    def _parse_timestamp(ts_str: str) -> float:
        """
        Parse ISO 8601 timestamp to Unix timestamp

        Args:
            ts_str: ISO 8601 formatted timestamp (e.g., "2025-01-31T10:00:00Z")

        Returns:
            float: Unix timestamp (seconds since epoch)
        """
        if not ts_str:
            return 0

        # Handle 'Z' suffix and '+00:00' timezone
        ts_str = ts_str.replace("Z", "+00:00")

        dt = datetime.fromisoformat(ts_str)
        return dt.timestamp()

    def is_expired(self) -> bool:
        """
        Check if account has expired (30-day trial period ended)

        Returns:
            bool: True if account expired
        """
        current_time = time.time()

        # Method 1: Use explicit expiry time if provided
        if self.expires_at:
            return current_time > self.expires_at

        # Method 2: Calculate based on creation time (30 days = 2592000 seconds)
        age_seconds = current_time - self.created_at
        age_days = age_seconds / 86400

        return age_days >= 30

    def get_remaining_days(self) -> int:
        """
        Get remaining days until expiry

        Returns:
            int: Remaining days (0 if expired)
        """
        current_time = time.time()

        if self.expires_at:
            remaining_seconds = self.expires_at - current_time
        else:
            # 30 days = 2592000 seconds
            age_seconds = current_time - self.created_at
            remaining_seconds = 2592000 - age_seconds

        remaining_days = remaining_seconds / 86400
        return max(0, int(remaining_days))

    def should_warn_expiry(self) -> bool:
        """
        Check if should warn about impending expiry

        Returns:
            bool: True if remaining < 3 days
        """
        remaining = self.get_remaining_days()
        return 0 < remaining < 3

    def get_account_age_days(self) -> int:
        """
        Get account age in days

        Returns:
            int: Days since account creation
        """
        age_seconds = time.time() - self.created_at
        return int(age_seconds / 86400)

    def is_in_cooldown(self) -> bool:
        """
        Check if account is in cooldown period

        Returns:
            bool: True if in cooldown
        """
        if self.cooldown_until == 0:
            return False

        current_time = time.time()
        if current_time >= self.cooldown_until:
            # Cooldown period ended, reset
            self.cooldown_until = 0
            if self.status in [
                AccountStatus.COOLDOWN_401,
                AccountStatus.COOLDOWN_403,
                AccountStatus.COOLDOWN_429,
            ]:
                self.status = AccountStatus.ACTIVE
            return False

        return True

    def set_cooldown(self, seconds: int, status: AccountStatus) -> None:
        """
        Set account cooldown period

        Args:
            seconds: Cooldown duration in seconds
            status: AccountStatus to set (COOLDOWN_401, COOLDOWN_403, COOLDOWN_429)
        """
        self.cooldown_until = time.time() + seconds
        self.status = status
        self.error_count += 1

    def is_available(self) -> bool:
        """
        Check if account is available for use

        Returns:
            bool: True if account is available (not expired, not in cooldown)
        """
        # Check expiry
        if self.is_expired():
            self.status = AccountStatus.EXPIRED
            return False

        # Check cooldown
        if self.is_in_cooldown():
            return False

        # Check status
        if self.status in [AccountStatus.EXPIRED, AccountStatus.ERROR]:
            return False

        return True

    def mark_used(self) -> None:
        """Mark account as used (update last_used_at and request_count)"""
        self.last_used_at = time.time()
        self.request_count += 1

    def get_status_info(self) -> dict:
        """
        Get account status information for monitoring

        Returns:
            dict: Account status details
        """
        current_time = time.time()
        cooldown_remaining = max(0, int(self.cooldown_until - current_time))

        return {
            "email": self.email,
            "team_id": self.team_id,
            "status": self.status.value,
            "is_available": self.is_available(),
            "is_expired": self.is_expired(),
            "age_days": self.get_account_age_days(),
            "remaining_days": self.get_remaining_days(),
            "cooldown_remaining": cooldown_remaining,
            "request_count": self.request_count,
            "error_count": self.error_count,
            "token_status": self.token_manager.get_status(),
        }
