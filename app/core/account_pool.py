"""
Account Pool - Multi-account management with rotation and lifecycle

Manages multiple Gemini Business accounts with:
- Round-robin rotation
- Automatic cooldown management
- 30-day lifecycle tracking
- Expired account cleanup
- Error handling and failover
"""

import asyncio
import logging
from typing import List, Optional

from app.models.account import Account, AccountStatus

logger = logging.getLogger(__name__)


class AccountPool:
    """
    Account Pool Manager

    Manages multiple accounts with round-robin rotation, cooldown, and lifecycle
    """

    def __init__(self):
        """Initialize Account Pool"""
        self.accounts: List[Account] = []
        self._current_index: int = 0
        self._lock = asyncio.Lock()

    def add_account(self, account: Account) -> None:
        """
        Add account to pool

        Args:
            account: Account instance to add
        """
        self.accounts.append(account)
        logger.info(
            f"Added account: {account.email} (team_id: {account.team_id}, "
            f"age: {account.get_account_age_days()}d, "
            f"remaining: {account.get_remaining_days()}d)"
        )

        # Warn if account is expiring soon
        if account.should_warn_expiry():
            logger.warning(
                f"⚠️ Account expiring soon: {account.email} "
                f"(remaining: {account.get_remaining_days()}d)"
            )

    async def get_available_account(self) -> Account:
        """
        Get next available account using round-robin

        Returns:
            Account: Next available account

        Raises:
            Exception: If no accounts available
        """
        async with self._lock:
            if not self.accounts:
                raise Exception("No accounts configured in pool")

            # Try each account starting from current index
            attempts = 0
            max_attempts = len(self.accounts)

            while attempts < max_attempts:
                account = self.accounts[self._current_index]

                # Move to next account for next call (round-robin)
                self._current_index = (self._current_index + 1) % len(self.accounts)
                attempts += 1

                # Check if account is available
                if account.is_available():
                    account.mark_used()
                    logger.debug(
                        f"Using account: {account.email} "
                        f"(requests: {account.request_count})"
                    )
                    return account
                else:
                    # Log why account is unavailable
                    if account.is_expired():
                        logger.debug(
                            f"Skipping expired account: {account.email} "
                            f"(age: {account.get_account_age_days()}d)"
                        )
                    elif account.is_in_cooldown():
                        logger.debug(
                            f"Skipping cooldown account: {account.email} "
                            f"(status: {account.status.value})"
                        )

            # No available accounts
            raise Exception("No available accounts (all in cooldown or expired)")

    def handle_error(
        self, account: Account, status_code: int, error_message: str
    ) -> None:
        """
        Handle account error and set cooldown if needed

        Args:
            account: Account that encountered error
            status_code: HTTP status code
            error_message: Error message
        """
        if status_code == 401:
            # Authentication error - 2 hour cooldown
            account.set_cooldown(7200, AccountStatus.COOLDOWN_401)
            logger.warning(
                f"⚠️ Account 401 error: {account.email} - "
                f"Cooldown for 2 hours ({error_message})"
            )

        elif status_code == 403:
            # Forbidden error - 2 hour cooldown
            account.set_cooldown(7200, AccountStatus.COOLDOWN_403)
            logger.warning(
                f"⚠️ Account 403 error: {account.email} - "
                f"Cooldown for 2 hours ({error_message})"
            )

        elif status_code == 429:
            # Rate limit - 4 hour cooldown
            account.set_cooldown(14400, AccountStatus.COOLDOWN_429)
            logger.warning(
                f"⚠️ Account 429 rate limit: {account.email} - "
                f"Cooldown for 4 hours ({error_message})"
            )

        else:
            # Other errors - increment error count
            account.error_count += 1
            logger.error(
                f"❌ Account error {status_code}: {account.email} - {error_message}"
            )

            # Mark as ERROR if too many consecutive failures
            if account.error_count >= 5:
                account.status = AccountStatus.ERROR
                logger.error(
                    f"❌ Account disabled due to multiple errors: {account.email}"
                )

    def cleanup_expired_accounts(self) -> int:
        """
        Remove expired accounts from pool

        Returns:
            int: Number of accounts removed
        """
        initial_count = len(self.accounts)
        expired_accounts = []
        active_accounts = []

        for account in self.accounts:
            if account.is_expired():
                expired_accounts.append(account)
                logger.info(
                    f"🗑️ Removing expired account: {account.email} "
                    f"(age: {account.get_account_age_days()}d)"
                )
            else:
                active_accounts.append(account)

        # Update account list
        self.accounts = active_accounts

        # Reset index if needed
        if self._current_index >= len(self.accounts):
            self._current_index = 0

        removed_count = initial_count - len(self.accounts)

        if removed_count > 0:
            logger.info(
                f"✅ Cleanup complete: Removed {removed_count} expired account(s), "
                f"{len(self.accounts)} active account(s) remaining"
            )

        return removed_count

    def warn_expiring_accounts(self) -> List[Account]:
        """
        Check and warn about accounts expiring soon (< 3 days)

        Returns:
            List[Account]: List of accounts expiring soon
        """
        expiring_accounts = []

        for account in self.accounts:
            if account.should_warn_expiry():
                expiring_accounts.append(account)
                remaining = account.get_remaining_days()

                if remaining == 0:
                    logger.error(
                        f"🔴 Account expires TODAY: {account.email} "
                        f"- Please prepare new account immediately!"
                    )
                elif remaining == 1:
                    logger.error(
                        f"🟠 Account expires TOMORROW: {account.email} "
                        f"- Register new account now!"
                    )
                else:
                    logger.warning(
                        f"⚠️ Account expiring soon: {account.email} "
                        f"(remaining: {remaining}d) - Prepare new account"
                    )

        return expiring_accounts

    def get_pool_status(self) -> dict:
        """
        Get account pool status for monitoring

        Returns:
            dict: Pool status information
        """
        total = len(self.accounts)
        active = len([a for a in self.accounts if a.is_available()])  # Changed: use is_available()
        cooldown = len(
            [
                a
                for a in self.accounts
                if a.status
                in [
                    AccountStatus.COOLDOWN_401,
                    AccountStatus.COOLDOWN_403,
                    AccountStatus.COOLDOWN_429,
                ]
            ]
        )
        expired = len([a for a in self.accounts if a.is_expired()])
        expiring_soon = len([a for a in self.accounts if a.should_warn_expiry()])

        # Calculate average age
        avg_age = (
            sum(a.get_account_age_days() for a in self.accounts) / total
            if total > 0
            else 0
        )

        return {
            "total": total,
            "active": active,
            "cooldown": cooldown,
            "expired": expired,
            "expiring_soon": expiring_soon,
            "average_age_days": round(avg_age, 1),
        }

    def get_accounts_status(self) -> List[dict]:
        """
        Get detailed status for all accounts

        Returns:
            List[dict]: List of account status details
        """
        return [account.get_status_info() for account in self.accounts]
