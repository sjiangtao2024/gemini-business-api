"""
Status Routes - API endpoints for system health and monitoring

Provides endpoints for:
- Health checks
- Account pool status
- Individual account status
"""

import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.account_pool import AccountPool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/status", tags=["status"])

# Global account pool (shared with chat routes)
account_pool: Optional[AccountPool] = None


def set_account_pool(pool: AccountPool) -> None:
    """
    Set the global account pool instance

    Args:
        pool: AccountPool instance
    """
    global account_pool
    account_pool = pool


# Response Models
class HealthResponse(BaseModel):
    """Health check response"""

    status: str = Field(..., description="Service status (healthy/degraded/unhealthy)")
    version: str = Field(..., description="API version")
    accounts_total: int = Field(..., description="Total accounts in pool")
    accounts_active: int = Field(..., description="Active accounts available")


class PoolStatusResponse(BaseModel):
    """Account pool status response"""

    total: int = Field(..., description="Total accounts")
    active: int = Field(..., description="Active accounts")
    cooldown: int = Field(..., description="Accounts in cooldown")
    expired: int = Field(..., description="Expired accounts")
    expiring_soon: int = Field(..., description="Accounts expiring soon (<3 days)")
    average_age_days: float = Field(..., description="Average account age in days")


class AccountStatusResponse(BaseModel):
    """Individual account status response"""

    email: str
    team_id: str
    status: str
    is_available: bool
    is_expired: bool
    age_days: int
    remaining_days: int
    cooldown_remaining: int
    request_count: int
    error_count: int
    token_status: Dict


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Health check endpoint

    Returns service health status based on available accounts.

    Returns:
        HealthResponse: Service health information

    Status determination:
    - healthy: 50%+ accounts active
    - degraded: 1-49% accounts active
    - unhealthy: 0% accounts active
    """
    if account_pool is None:
        raise HTTPException(
            status_code=503,
            detail="Service unavailable: Account pool not initialized",
        )

    pool_status = account_pool.get_pool_status()

    total = pool_status["total"]
    active = pool_status["active"]

    # Determine health status
    if total == 0:
        status = "unhealthy"
    elif active == 0:
        status = "unhealthy"
    elif active / total >= 0.5:
        status = "healthy"
    else:
        status = "degraded"

    return HealthResponse(
        status=status,
        version="1.0.0",
        accounts_total=total,
        accounts_active=active,
    )


@router.get("/pool", response_model=PoolStatusResponse)
async def get_pool_status() -> PoolStatusResponse:
    """
    Get account pool status

    Returns detailed statistics about the account pool.

    Returns:
        PoolStatusResponse: Pool status information

    Raises:
        HTTPException: If account pool not initialized
    """
    if account_pool is None:
        raise HTTPException(
            status_code=503,
            detail="Service unavailable: Account pool not initialized",
        )

    status = account_pool.get_pool_status()

    return PoolStatusResponse(
        total=status["total"],
        active=status["active"],
        cooldown=status["cooldown"],
        expired=status["expired"],
        expiring_soon=status["expiring_soon"],
        average_age_days=status["average_age_days"],
    )


@router.get("/accounts", response_model=List[AccountStatusResponse])
async def get_accounts_status() -> List[AccountStatusResponse]:
    """
    Get detailed status for all accounts

    Returns status information for each account in the pool.

    Returns:
        List[AccountStatusResponse]: List of account statuses

    Raises:
        HTTPException: If account pool not initialized
    """
    if account_pool is None:
        raise HTTPException(
            status_code=503,
            detail="Service unavailable: Account pool not initialized",
        )

    accounts_status = account_pool.get_accounts_status()

    return [
        AccountStatusResponse(
            email=status["email"],
            team_id=status["team_id"],
            status=status["status"],
            is_available=status["is_available"],
            is_expired=status["is_expired"],
            age_days=status["age_days"],
            remaining_days=status["remaining_days"],
            cooldown_remaining=status["cooldown_remaining"],
            request_count=status["request_count"],
            error_count=status["error_count"],
            token_status=status["token_status"],
        )
        for status in accounts_status
    ]
