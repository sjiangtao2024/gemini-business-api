"""
Unit tests for Account model

Tests 30-day lifecycle management, cooldown, and status tracking.
"""

import time
from datetime import datetime, timedelta, timezone

import pytest

from app.models.account import Account, AccountStatus


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
def fresh_account(account_data):
    """Create a fresh account (just created)"""
    return Account(**account_data)


@pytest.fixture
def old_account(account_data):
    """Create an old account (created 28 days ago)"""
    old_date = datetime.now(timezone.utc) - timedelta(days=28)
    account_data["created_at"] = old_date.isoformat()
    return Account(**account_data)


@pytest.fixture
def expired_account(account_data):
    """Create an expired account (created 31 days ago)"""
    expired_date = datetime.now(timezone.utc) - timedelta(days=31)
    account_data["created_at"] = expired_date.isoformat()
    return Account(**account_data)


class TestAccountInit:
    """Test Account initialization"""

    def test_init_sets_credentials(self, fresh_account):
        """Test that initialization sets all credentials correctly"""
        assert fresh_account.email == "test@example.com"
        assert fresh_account.team_id == "test-team-id"
        assert fresh_account.secure_c_ses == "test-secure-c-ses"
        assert fresh_account.host_c_oses == "test-host-c-oses"
        assert fresh_account.csesidx == "123456"
        assert fresh_account.user_agent == "test-user-agent"

    def test_init_sets_default_status(self, fresh_account):
        """Test that initialization sets default status"""
        assert fresh_account.status == AccountStatus.ACTIVE
        assert fresh_account.cooldown_until == 0
        assert fresh_account.request_count == 0
        assert fresh_account.error_count == 0

    def test_init_creates_token_manager(self, fresh_account):
        """Test that initialization creates TokenManager instance"""
        assert fresh_account.token_manager is not None
        assert fresh_account.token_manager.team_id == "test-team-id"


class TestAccountExpiry:
    """Test 30-day expiry logic"""

    def test_fresh_account_not_expired(self, fresh_account):
        """Fresh account should not be expired"""
        assert fresh_account.is_expired() is False

    def test_old_account_not_expired(self, old_account):
        """28-day old account should not be expired"""
        assert old_account.is_expired() is False

    def test_expired_account_is_expired(self, expired_account):
        """31-day old account should be expired"""
        assert expired_account.is_expired() is True

    def test_expiry_with_explicit_expires_at(self, account_data):
        """Test expiry with explicit expires_at field"""
        # Set expires_at to 1 day ago
        past = datetime.now(timezone.utc) - timedelta(days=1)
        account_data["expires_at"] = past.isoformat()

        account = Account(**account_data)
        assert account.is_expired() is True

    def test_not_expired_with_future_expires_at(self, account_data):
        """Test not expired with future expires_at"""
        future = datetime.now(timezone.utc) + timedelta(days=10)
        account_data["expires_at"] = future.isoformat()

        account = Account(**account_data)
        assert account.is_expired() is False


class TestAccountRemainingDays:
    """Test remaining days calculation"""

    def test_fresh_account_remaining_days(self, fresh_account):
        """Fresh account should have ~30 days remaining"""
        remaining = fresh_account.get_remaining_days()
        assert 29 <= remaining <= 30

    def test_old_account_remaining_days(self, old_account):
        """28-day old account should have ~2 days remaining"""
        remaining = old_account.get_remaining_days()
        assert 1 <= remaining <= 3

    def test_expired_account_remaining_days(self, expired_account):
        """Expired account should have 0 days remaining"""
        remaining = expired_account.get_remaining_days()
        assert remaining == 0


class TestAccountExpiryWarning:
    """Test expiry warning logic"""

    def test_fresh_account_no_warning(self, fresh_account):
        """Fresh account should not trigger warning"""
        assert fresh_account.should_warn_expiry() is False

    def test_old_account_should_warn(self, old_account):
        """28-day old account should trigger warning"""
        assert old_account.should_warn_expiry() is True

    def test_expired_account_no_warning(self, expired_account):
        """Expired account should not trigger warning (already expired)"""
        assert expired_account.should_warn_expiry() is False


class TestAccountAge:
    """Test account age calculation"""

    def test_fresh_account_age(self, fresh_account):
        """Fresh account should be 0 days old"""
        age = fresh_account.get_account_age_days()
        assert age == 0

    def test_old_account_age(self, old_account):
        """Old account should be ~28 days old"""
        age = old_account.get_account_age_days()
        assert 27 <= age <= 29

    def test_expired_account_age(self, expired_account):
        """Expired account should be ~31 days old"""
        age = expired_account.get_account_age_days()
        assert 30 <= age <= 32


class TestAccountCooldown:
    """Test cooldown management"""

    def test_not_in_cooldown_initially(self, fresh_account):
        """Account should not be in cooldown initially"""
        assert fresh_account.is_in_cooldown() is False

    def test_in_cooldown_after_set(self, fresh_account):
        """Account should be in cooldown after set_cooldown"""
        fresh_account.set_cooldown(3600, AccountStatus.COOLDOWN_401)

        assert fresh_account.is_in_cooldown() is True
        assert fresh_account.status == AccountStatus.COOLDOWN_401
        assert fresh_account.error_count == 1

    def test_cooldown_expires(self, fresh_account):
        """Cooldown should expire after time passes"""
        # Set cooldown for 1 second
        fresh_account.set_cooldown(1, AccountStatus.COOLDOWN_401)

        assert fresh_account.is_in_cooldown() is True

        # Wait for cooldown to expire (add more buffer time)
        time.sleep(1.2)

        assert fresh_account.is_in_cooldown() is False
        assert fresh_account.status == AccountStatus.ACTIVE

    def test_set_cooldown_increments_error_count(self, fresh_account):
        """set_cooldown should increment error_count"""
        initial_count = fresh_account.error_count

        fresh_account.set_cooldown(3600, AccountStatus.COOLDOWN_429)

        assert fresh_account.error_count == initial_count + 1


class TestAccountAvailability:
    """Test is_available logic"""

    def test_fresh_account_available(self, fresh_account):
        """Fresh account should be available"""
        assert fresh_account.is_available() is True

    def test_expired_account_not_available(self, expired_account):
        """Expired account should not be available"""
        assert expired_account.is_available() is False
        assert expired_account.status == AccountStatus.EXPIRED

    def test_cooldown_account_not_available(self, fresh_account):
        """Account in cooldown should not be available"""
        fresh_account.set_cooldown(3600, AccountStatus.COOLDOWN_401)

        assert fresh_account.is_available() is False

    def test_error_account_not_available(self, fresh_account):
        """Account with ERROR status should not be available"""
        fresh_account.status = AccountStatus.ERROR

        assert fresh_account.is_available() is False


class TestAccountMarkUsed:
    """Test mark_used method"""

    def test_mark_used_increments_count(self, fresh_account):
        """mark_used should increment request_count"""
        initial_count = fresh_account.request_count

        fresh_account.mark_used()

        assert fresh_account.request_count == initial_count + 1

    def test_mark_used_updates_last_used(self, fresh_account):
        """mark_used should update last_used_at timestamp"""
        initial_time = fresh_account.last_used_at

        time.sleep(0.1)
        fresh_account.mark_used()

        assert fresh_account.last_used_at > initial_time


class TestAccountStatus:
    """Test get_status_info method"""

    def test_status_info_structure(self, fresh_account):
        """Status info should have all required fields"""
        status = fresh_account.get_status_info()

        assert "email" in status
        assert "team_id" in status
        assert "status" in status
        assert "is_available" in status
        assert "is_expired" in status
        assert "age_days" in status
        assert "remaining_days" in status
        assert "cooldown_remaining" in status
        assert "request_count" in status
        assert "error_count" in status
        assert "token_status" in status

    def test_status_info_values(self, fresh_account):
        """Status info should have correct values"""
        status = fresh_account.get_status_info()

        assert status["email"] == "test@example.com"
        assert status["is_available"] is True
        assert status["is_expired"] is False
        assert status["cooldown_remaining"] == 0


class TestParseTimestamp:
    """Test _parse_timestamp static method"""

    def test_parse_iso8601_with_z(self):
        """Parse ISO 8601 timestamp with Z suffix"""
        ts_str = "2025-01-31T10:00:00Z"
        timestamp = Account._parse_timestamp(ts_str)

        assert timestamp > 0
        assert isinstance(timestamp, float)

    def test_parse_iso8601_with_timezone(self):
        """Parse ISO 8601 timestamp with timezone"""
        ts_str = "2025-01-31T10:00:00+00:00"
        timestamp = Account._parse_timestamp(ts_str)

        assert timestamp > 0

    def test_parse_empty_string(self):
        """Parse empty string returns 0"""
        timestamp = Account._parse_timestamp("")

        assert timestamp == 0
