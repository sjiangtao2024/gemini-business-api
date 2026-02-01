"""
Admin API Routes - 管理界面后端 API

提供账号管理、日志查看、统计信息等管理功能。
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, EmailStr

from app.core.account_pool import AccountPool
from app.models.account import Account

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

# 全局账号池
account_pool: Optional[AccountPool] = None

# 日志缓冲区（用于 SSE 流式输出）
log_buffer: List[Dict[str, Any]] = []
MAX_LOG_BUFFER_SIZE = 1000


def set_account_pool(pool: AccountPool) -> None:
    """设置全局账号池"""
    global account_pool
    account_pool = pool


class LogHandler(logging.Handler):
    """自定义日志处理器，将日志添加到缓冲区"""

    def emit(self, record: logging.LogRecord) -> None:
        """处理日志记录"""
        try:
            log_entry = {
                "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }

            # 添加到缓冲区
            log_buffer.append(log_entry)

            # 限制缓冲区大小
            if len(log_buffer) > MAX_LOG_BUFFER_SIZE:
                log_buffer.pop(0)

        except Exception:
            self.handleError(record)


# 注册日志处理器
log_handler = LogHandler()
log_handler.setLevel(logging.INFO)
logging.getLogger().addHandler(log_handler)


# 请求/响应模型
class AddAccountRequest(BaseModel):
    """添加账号请求"""
    email: EmailStr = Field(..., description="账号邮箱")
    team_id: str = Field(..., description="团队 ID")
    secure_c_ses: str = Field(..., description="__Secure-c-SES Cookie")
    host_c_oses: str = Field(..., description="__Host-c-OSES Cookie")
    csesidx: str = Field(..., description="csesidx Cookie")
    user_agent: str = Field(..., description="User-Agent")
    created_at: Optional[str] = Field(None, description="创建时间 (ISO 8601)")
    expires_at: Optional[str] = Field(None, description="过期时间 (ISO 8601)")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "email": "gemini1@goodcv.fun",
                    "team_id": "1d468dcc-11a5-4adc-8b68-8098e227000c",
                    "secure_c_ses": "CSE.xxx...",
                    "host_c_oses": "COS.xxx...",
                    "csesidx": "206226908",
                    "user_agent": "Mozilla/5.0 ...",
                    "created_at": "2025-01-31T10:00:00Z",
                    "expires_at": "2025-03-02T10:00:00Z"
                }
            ]
        }
    }


class AccountStatusResponse(BaseModel):
    """账号状态响应"""
    email: str
    team_id: str
    status: str  # active, cooldown, expired
    created_at: str
    expires_at: str
    remaining_days: int
    last_used_at: Optional[str] = None
    cooldown_until: Optional[str] = None
    total_requests: int
    failed_requests: int


class StatsResponse(BaseModel):
    """统计信息响应"""
    total_accounts: int
    active_accounts: int
    cooldown_accounts: int
    expired_accounts: int
    total_requests: int
    successful_requests: int
    failed_requests: int
    success_rate: float


@router.get("/accounts", response_model=List[AccountStatusResponse])
async def list_accounts():
    """
    获取账号列表

    返回所有账号的详细状态信息，包括：
    - 账号基本信息
    - 当前状态（active/cooldown/expired）
    - 剩余天数
    - 使用统计
    """
    if account_pool is None:
        raise HTTPException(
            status_code=503,
            detail="Service unavailable: Account pool not initialized"
        )

    accounts_status = []

    for account in account_pool.accounts:
        # 计算剩余天数
        remaining_days = account.get_remaining_days()

        # 判断状态
        if account.is_expired():
            status = "expired"
        elif account.is_in_cooldown():
            status = "cooldown"
        else:
            status = "active"

        # 获取冷却结束时间
        cooldown_until = None
        if account.cooldown_until > 0:
            cooldown_until = datetime.fromtimestamp(
                account.cooldown_until,
                tz=timezone.utc
            ).isoformat()

        # 获取最后使用时间
        last_used_at = None
        if account.last_used_at > 0:
            last_used_at = datetime.fromtimestamp(
                account.last_used_at,
                tz=timezone.utc
            ).isoformat()

        accounts_status.append(AccountStatusResponse(
            email=account.email,
            team_id=account.team_id,
            status=status,
            created_at=datetime.fromtimestamp(
                account.created_at, tz=timezone.utc
            ).isoformat(),
            expires_at=datetime.fromtimestamp(
                account.expires_at, tz=timezone.utc
            ).isoformat() if account.expires_at else None,
            remaining_days=remaining_days,
            last_used_at=last_used_at,
            cooldown_until=cooldown_until,
            total_requests=account.request_count,
            failed_requests=account.error_count
        ))

    return accounts_status


@router.post("/accounts")
async def add_account(request: AddAccountRequest):
    """
    添加新账号

    验证账号信息并添加到账号池，同时更新配置文件。
    """
    if account_pool is None:
        raise HTTPException(
            status_code=503,
            detail="Service unavailable: Account pool not initialized"
        )

    # 检查账号是否已存在
    for account in account_pool.accounts:
        if account.email == request.email:
            raise HTTPException(
                status_code=400,
                detail=f"Account {request.email} already exists"
            )

    # 创建账号对象
    try:
        # 使用当前时间作为默认创建时间
        created_at = request.created_at or datetime.now(timezone.utc).isoformat()

        # 计算过期时间（默认 30 天后）
        if request.expires_at:
            expires_at = request.expires_at
        else:
            created_timestamp = datetime.fromisoformat(created_at.replace('Z', '+00:00')).timestamp()
            expires_timestamp = created_timestamp + (30 * 24 * 3600)
            expires_at = datetime.fromtimestamp(expires_timestamp, tz=timezone.utc).isoformat()

        account = Account(
            email=request.email,
            team_id=request.team_id,
            secure_c_ses=request.secure_c_ses,
            host_c_oses=request.host_c_oses,
            csesidx=request.csesidx,
            user_agent=request.user_agent,
            created_at=created_at,
            expires_at=expires_at
        )

        # 添加到账号池
        account_pool.add_account(account)

        # 更新配置文件
        await update_accounts_config()

        logger.info(f"✅ Added new account: {account.email}")

        return {
            "message": f"Account {account.email} added successfully",
            "email": account.email,
            "remaining_days": account_pool.get_remaining_days(account)
        }

    except Exception as e:
        logger.error(f"❌ Failed to add account: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to add account: {str(e)}"
        )


@router.delete("/accounts/{email}")
async def delete_account(email: str):
    """
    删除账号

    从账号池移除账号，并更新配置文件。
    """
    if account_pool is None:
        raise HTTPException(
            status_code=503,
            detail="Service unavailable: Account pool not initialized"
        )

    # 查找账号
    account_to_remove = None
    for account in account_pool.accounts:
        if account.email == email:
            account_to_remove = account
            break

    if account_to_remove is None:
        raise HTTPException(
            status_code=404,
            detail=f"Account {email} not found"
        )

    # 从账号池移除
    account_pool.accounts.remove(account_to_remove)

    # 清理相关数据
    if email in account_pool.cooldown_until:
        del account_pool.cooldown_until[email]
    if email in account_pool.last_used:
        del account_pool.last_used[email]
    if email in account_pool.request_count:
        del account_pool.request_count[email]
    if email in account_pool.error_count:
        del account_pool.error_count[email]

    # 更新配置文件
    await update_accounts_config()

    logger.info(f"🗑️ Deleted account: {email}")

    return {
        "message": f"Account {email} deleted successfully",
        "remaining_accounts": len(account_pool.accounts)
    }


@router.get("/stats", response_model=StatsResponse)
async def get_stats():
    """
    获取统计信息

    返回账号池的总体统计数据。
    """
    if account_pool is None:
        raise HTTPException(
            status_code=503,
            detail="Service unavailable: Account pool not initialized"
        )

    # 统计各状态账号数量
    total_accounts = len(account_pool.accounts)
    active_accounts = 0
    cooldown_accounts = 0
    expired_accounts = 0

    for account in account_pool.accounts:
        if account_pool.is_expired(account):
            expired_accounts += 1
        elif account_pool.is_in_cooldown(account):
            cooldown_accounts += 1
        else:
            active_accounts += 1

    # 统计请求数据
    total_requests = sum(account_pool.request_count.values())
    failed_requests = sum(account_pool.error_count.values())
    successful_requests = total_requests - failed_requests
    success_rate = (successful_requests / total_requests * 100) if total_requests > 0 else 0.0

    return StatsResponse(
        total_accounts=total_accounts,
        active_accounts=active_accounts,
        cooldown_accounts=cooldown_accounts,
        expired_accounts=expired_accounts,
        total_requests=total_requests,
        successful_requests=successful_requests,
        failed_requests=failed_requests,
        success_rate=round(success_rate, 2)
    )


@router.get("/logs/stream")
async def stream_logs():
    """
    SSE 日志流

    实时推送日志到前端。
    """
    async def event_generator():
        """生成 SSE 事件"""
        # 发送历史日志
        for log_entry in log_buffer[-100:]:  # 最近 100 条
            yield f"event: log\ndata: {json.dumps(log_entry)}\n\n"

        # 持续发送新日志
        last_index = len(log_buffer)
        while True:
            # 检查是否有新日志
            if len(log_buffer) > last_index:
                for log_entry in log_buffer[last_index:]:
                    yield f"event: log\ndata: {json.dumps(log_entry)}\n\n"
                last_index = len(log_buffer)

            # 发送心跳包
            yield f"event: ping\ndata: {json.dumps({'timestamp': time.time()})}\n\n"

            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


async def update_accounts_config():
    """更新账号配置文件"""
    if account_pool is None:
        return

    try:
        # 读取当前配置
        config_path = "config/accounts.json"

        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        # 更新账号列表
        config["accounts"] = [
            {
                "email": account.email,
                "team_id": account.team_id,
                "secure_c_ses": account.secure_c_ses,
                "host_c_oses": account.host_c_oses,
                "csesidx": account.csesidx,
                "user_agent": account.user_agent,
                "created_at": account.created_at,
                "expires_at": account.expires_at
            }
            for account in account_pool.accounts
        ]

        # 写回配置文件
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        logger.debug(f"📝 Updated accounts config: {len(account_pool.accounts)} accounts")

    except Exception as e:
        logger.error(f"❌ Failed to update config: {e}")
        raise
