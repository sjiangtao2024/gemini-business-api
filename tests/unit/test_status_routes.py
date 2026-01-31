"""
Unit tests for Status Routes

Tests API endpoints for health checks and monitoring.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.core.account_pool import AccountPool
from app.models.account import Account, AccountStatus
from app.routes.status import (
    get_accounts_status,
    get_pool_status,
    health_check,
    set_account_pool,
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
def mock_pool():
    """Create mock account pool"""
    pool = MagicMock(spec=AccountPool)
    return pool


@pytest.fixture
def setup_pool(mock_pool):
    """Setup account pool for routes"""
    set_account_pool(mock_pool)
    yield
    set_account_pool(None)


class TestHealthCheck:
    """Test health_check endpoint"""

    @pytest.mark.asyncio
    async def test_health_check_healthy(self, setup_pool, mock_pool):
        """Health check with 50%+ active accounts"""
        mock_pool.get_pool_status.return_value = {
            "total": 10,
            "active": 8,
            "cooldown": 1,
            "expired": 1,
            "expiring_soon": 0,
            "average_age_days": 15.0,
        }

        response = await health_check()

        assert response.status == "healthy"
        assert response.version == "1.0.0"
        assert response.accounts_total == 10
        assert response.accounts_active == 8

    @pytest.mark.asyncio
    async def test_health_check_degraded(self, setup_pool, mock_pool):
        """Health check with <50% active accounts"""
        mock_pool.get_pool_status.return_value = {
            "total": 10,
            "active": 3,
            "cooldown": 5,
            "expired": 2,
            "expiring_soon": 1,
            "average_age_days": 20.0,
        }

        response = await health_check()

        assert response.status == "degraded"
        assert response.accounts_total == 10
        assert response.accounts_active == 3

    @pytest.mark.asyncio
    async def test_health_check_unhealthy_no_active(self, setup_pool, mock_pool):
        """Health check with 0 active accounts"""
        mock_pool.get_pool_status.return_value = {
            "total": 5,
            "active": 0,
            "cooldown": 3,
            "expired": 2,
            "expiring_soon": 0,
            "average_age_days": 25.0,
        }

        response = await health_check()

        assert response.status == "unhealthy"
        assert response.accounts_total == 5
        assert response.accounts_active == 0

    @pytest.mark.asyncio
    async def test_health_check_unhealthy_no_accounts(self, setup_pool, mock_pool):
        """Health check with 0 total accounts"""
        mock_pool.get_pool_status.return_value = {
            "total": 0,
            "active": 0,
            "cooldown": 0,
            "expired": 0,
            "expiring_soon": 0,
            "average_age_days": 0.0,
        }

        response = await health_check()

        assert response.status == "unhealthy"
        assert response.accounts_total == 0
        assert response.accounts_active == 0

    @pytest.mark.asyncio
    async def test_health_check_no_pool(self):
        """Health check should fail if pool not initialized"""
        set_account_pool(None)

        with pytest.raises(HTTPException) as exc_info:
            await health_check()

        assert exc_info.value.status_code == 503
        assert "not initialized" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_health_check_exactly_50_percent(self, setup_pool, mock_pool):
        """Health check with exactly 50% active"""
        mock_pool.get_pool_status.return_value = {
            "total": 10,
            "active": 5,
            "cooldown": 3,
            "expired": 2,
            "expiring_soon": 0,
            "average_age_days": 15.0,
        }

        response = await health_check()

        assert response.status == "healthy"


class TestGetPoolStatus:
    """Test get_pool_status endpoint"""

    @pytest.mark.asyncio
    async def test_get_pool_status_success(self, setup_pool, mock_pool):
        """Get pool status successfully"""
        mock_pool.get_pool_status.return_value = {
            "total": 10,
            "active": 7,
            "cooldown": 2,
            "expired": 1,
            "expiring_soon": 1,
            "average_age_days": 18.5,
        }

        response = await get_pool_status()

        assert response.total == 10
        assert response.active == 7
        assert response.cooldown == 2
        assert response.expired == 1
        assert response.expiring_soon == 1
        assert response.average_age_days == 18.5

    @pytest.mark.asyncio
    async def test_get_pool_status_empty_pool(self, setup_pool, mock_pool):
        """Get status for empty pool"""
        mock_pool.get_pool_status.return_value = {
            "total": 0,
            "active": 0,
            "cooldown": 0,
            "expired": 0,
            "expiring_soon": 0,
            "average_age_days": 0.0,
        }

        response = await get_pool_status()

        assert response.total == 0
        assert response.active == 0
        assert response.average_age_days == 0.0

    @pytest.mark.asyncio
    async def test_get_pool_status_no_pool(self):
        """Get pool status should fail if pool not initialized"""
        set_account_pool(None)

        with pytest.raises(HTTPException) as exc_info:
            await get_pool_status()

        assert exc_info.value.status_code == 503


class TestGetAccountsStatus:
    """Test get_accounts_status endpoint"""

    @pytest.mark.asyncio
    async def test_get_accounts_status_success(self, setup_pool, mock_pool):
        """Get accounts status successfully"""
        mock_pool.get_accounts_status.return_value = [
            {
                "email": "test1@example.com",
                "team_id": "team-1",
                "status": "ACTIVE",
                "is_available": True,
                "is_expired": False,
                "age_days": 10,
                "remaining_days": 20,
                "cooldown_remaining": 0,
                "request_count": 100,
                "error_count": 0,
                "token_status": {"valid": True},
            },
            {
                "email": "test2@example.com",
                "team_id": "team-2",
                "status": "COOLDOWN_429",
                "is_available": False,
                "is_expired": False,
                "age_days": 15,
                "remaining_days": 15,
                "cooldown_remaining": 3600,
                "request_count": 200,
                "error_count": 1,
                "token_status": {"valid": True},
            },
        ]

        response = await get_accounts_status()

        assert len(response) == 2
        assert response[0].email == "test1@example.com"
        assert response[0].is_available is True
        assert response[1].email == "test2@example.com"
        assert response[1].status == "COOLDOWN_429"
        assert response[1].cooldown_remaining == 3600

    @pytest.mark.asyncio
    async def test_get_accounts_status_empty(self, setup_pool, mock_pool):
        """Get accounts status for empty pool"""
        mock_pool.get_accounts_status.return_value = []

        response = await get_accounts_status()

        assert len(response) == 0
        assert isinstance(response, list)

    @pytest.mark.asyncio
    async def test_get_accounts_status_no_pool(self):
        """Get accounts status should fail if pool not initialized"""
        set_account_pool(None)

        with pytest.raises(HTTPException) as exc_info:
            await get_accounts_status()

        assert exc_info.value.status_code == 503
