"""
Unit tests for AccountPool

Tests round-robin rotation, cooldown management, and lifecycle cleanup.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.core.account_pool import AccountPool
from app.models.account import Account, AccountStatus


@pytest.fixture
def account_pool():
    """Create an empty AccountPool"""
    return AccountPool()


@pytest.fixture
def fresh_account_data():
    """Fresh account data"""
    now = datetime.now(timezone.utc)
    return {
        "email": "fresh@example.com",
        "team_id": "fresh-team-id",
        "secure_c_ses": "fresh-ses",
        "host_c_oses": "fresh-oses",
        "csesidx": "111111",
        "user_agent": "fresh-ua",
        "created_at": now.isoformat(),
    }


@pytest.fixture
def expired_account_data():
    """Expired account data"""
    old_date = datetime.now(timezone.utc) - timedelta(days=31)
    return {
        "email": "expired@example.com",
        "team_id": "expired-team-id",
        "secure_c_ses": "expired-ses",
        "host_c_oses": "expired-oses",
        "csesidx": "222222",
        "user_agent": "expired-ua",
        "created_at": old_date.isoformat(),
    }


class TestAccountPoolInit:
    """Test AccountPool initialization"""

    def test_init_empty_pool(self, account_pool):
        """Pool should be empty on initialization"""
        assert len(account_pool.accounts) == 0
        assert account_pool._current_index == 0

    def test_init_creates_lock(self, account_pool):
        """Pool should create asyncio Lock"""
        assert isinstance(account_pool._lock, asyncio.Lock)


class TestAddAccount:
    """Test add_account method"""

    def test_add_single_account(self, account_pool, fresh_account_data):
        """Add single account to pool"""
        account = Account(**fresh_account_data)
        account_pool.add_account(account)

        assert len(account_pool.accounts) == 1
        assert account_pool.accounts[0] == account

    def test_add_multiple_accounts(self, account_pool, fresh_account_data):
        """Add multiple accounts to pool"""
        account1 = Account(**fresh_account_data)
        account2_data = fresh_account_data.copy()
        account2_data["email"] = "second@example.com"
        account2 = Account(**account2_data)

        account_pool.add_account(account1)
        account_pool.add_account(account2)

        assert len(account_pool.accounts) == 2


class TestGetAvailableAccount:
    """Test get_available_account method"""

    @pytest.mark.asyncio
    async def test_get_account_from_single(self, account_pool, fresh_account_data):
        """Get account from pool with single account"""
        account = Account(**fresh_account_data)
        account_pool.add_account(account)

        result = await account_pool.get_available_account()

        assert result == account
        assert result.request_count == 1

    @pytest.mark.asyncio
    async def test_round_robin_rotation(self, account_pool, fresh_account_data):
        """Test round-robin rotation across multiple accounts"""
        # Add 3 accounts
        accounts = []
        for i in range(3):
            data = fresh_account_data.copy()
            data["email"] = f"account{i}@example.com"
            data["team_id"] = f"team-{i}"
            account = Account(**data)
            accounts.append(account)
            account_pool.add_account(account)

        # Get accounts 4 times (should cycle: 0, 1, 2, 0)
        result1 = await account_pool.get_available_account()
        result2 = await account_pool.get_available_account()
        result3 = await account_pool.get_available_account()
        result4 = await account_pool.get_available_account()

        assert result1 == accounts[0]
        assert result2 == accounts[1]
        assert result3 == accounts[2]
        assert result4 == accounts[0]

    @pytest.mark.asyncio
    async def test_skip_cooldown_account(self, account_pool, fresh_account_data):
        """Skip account in cooldown"""
        # Add 2 accounts
        account1 = Account(**fresh_account_data)
        account2_data = fresh_account_data.copy()
        account2_data["email"] = "account2@example.com"
        account2 = Account(**account2_data)

        account_pool.add_account(account1)
        account_pool.add_account(account2)

        # Put account1 in cooldown
        account1.set_cooldown(3600, AccountStatus.COOLDOWN_401)

        # Should get account2 twice (skip account1)
        result1 = await account_pool.get_available_account()
        result2 = await account_pool.get_available_account()

        assert result1 == account2
        assert result2 == account2

    @pytest.mark.asyncio
    async def test_skip_expired_account(self, account_pool, fresh_account_data, expired_account_data):
        """Skip expired account"""
        fresh = Account(**fresh_account_data)
        expired = Account(**expired_account_data)

        account_pool.add_account(expired)
        account_pool.add_account(fresh)

        # Should get fresh account (skip expired)
        result = await account_pool.get_available_account()

        assert result == fresh

    @pytest.mark.asyncio
    async def test_no_available_accounts_raises(self, account_pool, expired_account_data):
        """Raise exception when no accounts available"""
        expired = Account(**expired_account_data)
        account_pool.add_account(expired)

        with pytest.raises(Exception, match="No available accounts"):
            await account_pool.get_available_account()

    @pytest.mark.asyncio
    async def test_empty_pool_raises(self, account_pool):
        """Raise exception when pool is empty"""
        with pytest.raises(Exception, match="No accounts configured"):
            await account_pool.get_available_account()


class TestHandleError:
    """Test handle_error method"""

    def test_handle_401_error(self, account_pool, fresh_account_data):
        """401 error should trigger 2-hour cooldown"""
        account = Account(**fresh_account_data)
        account_pool.add_account(account)

        account_pool.handle_error(account, 401, "Unauthorized")

        assert account.status == AccountStatus.COOLDOWN_401
        assert account.is_in_cooldown() is True
        assert account.error_count == 1

    def test_handle_403_error(self, account_pool, fresh_account_data):
        """403 error should trigger 2-hour cooldown"""
        account = Account(**fresh_account_data)
        account_pool.add_account(account)

        account_pool.handle_error(account, 403, "Forbidden")

        assert account.status == AccountStatus.COOLDOWN_403
        assert account.is_in_cooldown() is True

    def test_handle_429_error(self, account_pool, fresh_account_data):
        """429 error should trigger 4-hour cooldown"""
        account = Account(**fresh_account_data)
        account_pool.add_account(account)

        account_pool.handle_error(account, 429, "Rate limit")

        assert account.status == AccountStatus.COOLDOWN_429
        assert account.is_in_cooldown() is True

    def test_handle_other_error_increments_count(self, account_pool, fresh_account_data):
        """Other errors should increment error_count"""
        account = Account(**fresh_account_data)
        account_pool.add_account(account)

        initial_count = account.error_count
        account_pool.handle_error(account, 500, "Server error")

        assert account.error_count == initial_count + 1

    def test_multiple_errors_mark_as_error(self, account_pool, fresh_account_data):
        """5+ errors should mark account as ERROR"""
        account = Account(**fresh_account_data)
        account_pool.add_account(account)

        # Trigger 5 errors
        for i in range(5):
            account_pool.handle_error(account, 500, f"Error {i}")

        assert account.status == AccountStatus.ERROR


class TestCleanupExpiredAccounts:
    """Test cleanup_expired_accounts method"""

    def test_cleanup_removes_expired(self, account_pool, fresh_account_data, expired_account_data):
        """Cleanup should remove expired accounts"""
        fresh = Account(**fresh_account_data)
        expired = Account(**expired_account_data)

        account_pool.add_account(fresh)
        account_pool.add_account(expired)

        removed = account_pool.cleanup_expired_accounts()

        assert removed == 1
        assert len(account_pool.accounts) == 1
        assert account_pool.accounts[0] == fresh

    def test_cleanup_keeps_active(self, account_pool, fresh_account_data):
        """Cleanup should keep active accounts"""
        account = Account(**fresh_account_data)
        account_pool.add_account(account)

        removed = account_pool.cleanup_expired_accounts()

        assert removed == 0
        assert len(account_pool.accounts) == 1

    def test_cleanup_resets_index(self, account_pool, fresh_account_data, expired_account_data):
        """Cleanup should reset index if out of bounds"""
        expired = Account(**expired_account_data)
        account_pool.add_account(expired)

        # Set index beyond bounds
        account_pool._current_index = 5

        account_pool.cleanup_expired_accounts()

        assert account_pool._current_index == 0


class TestWarnExpiringAccounts:
    """Test warn_expiring_accounts method"""

    def test_warn_expiring_soon(self, account_pool):
        """Warn about accounts expiring soon"""
        # Create account expiring in 2 days
        expiring_date = datetime.now(timezone.utc) - timedelta(days=28)
        data = {
            "email": "expiring@example.com",
            "team_id": "expiring-team",
            "secure_c_ses": "ses",
            "host_c_oses": "oses",
            "csesidx": "123",
            "user_agent": "ua",
            "created_at": expiring_date.isoformat(),
        }
        account = Account(**data)
        account_pool.add_account(account)

        result = account_pool.warn_expiring_accounts()

        assert len(result) == 1
        assert result[0] == account

    def test_no_warning_for_fresh(self, account_pool, fresh_account_data):
        """No warning for fresh accounts"""
        account = Account(**fresh_account_data)
        account_pool.add_account(account)

        result = account_pool.warn_expiring_accounts()

        assert len(result) == 0


class TestGetPoolStatus:
    """Test get_pool_status method"""

    def test_pool_status_structure(self, account_pool):
        """Pool status should have all required fields"""
        status = account_pool.get_pool_status()

        assert "total" in status
        assert "active" in status
        assert "cooldown" in status
        assert "expired" in status
        assert "expiring_soon" in status
        assert "average_age_days" in status

    def test_pool_status_values(self, account_pool, fresh_account_data, expired_account_data):
        """Pool status should have correct values"""
        fresh = Account(**fresh_account_data)
        expired = Account(**expired_account_data)

        account_pool.add_account(fresh)
        account_pool.add_account(expired)

        status = account_pool.get_pool_status()

        assert status["total"] == 2
        assert status["active"] == 1
        assert status["expired"] == 1

    def test_empty_pool_status(self, account_pool):
        """Empty pool should have zero values"""
        status = account_pool.get_pool_status()

        assert status["total"] == 0
        assert status["active"] == 0
        assert status["average_age_days"] == 0


class TestGetAccountsStatus:
    """Test get_accounts_status method"""

    def test_accounts_status_list(self, account_pool, fresh_account_data):
        """Should return list of account statuses"""
        account = Account(**fresh_account_data)
        account_pool.add_account(account)

        statuses = account_pool.get_accounts_status()

        assert len(statuses) == 1
        assert isinstance(statuses[0], dict)
        assert statuses[0]["email"] == "fresh@example.com"

    def test_empty_pool_accounts_status(self, account_pool):
        """Empty pool should return empty list"""
        statuses = account_pool.get_accounts_status()

        assert len(statuses) == 0
        assert isinstance(statuses, list)
