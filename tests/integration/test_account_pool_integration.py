"""
集成测试 - 账号池与 Token 管理器集成

测试账号池、Token 管理器和配置加载器的集成工作流程。
"""

import asyncio
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import ConfigLoader
from app.core.account_pool import AccountPool
from app.models.account import Account, AccountStatus


@pytest.fixture
def valid_config_data():
    """有效的配置数据"""
    now = datetime.now(timezone.utc)
    return {
        "accounts": [
            {
                "email": "account1@example.com",
                "team_id": "team-1",
                "secure_c_ses": "ses-1",
                "host_c_oses": "oses-1",
                "csesidx": "111111",
                "user_agent": "ua-1",
                "created_at": now.isoformat(),
            },
            {
                "email": "account2@example.com",
                "team_id": "team-2",
                "secure_c_ses": "ses-2",
                "host_c_oses": "oses-2",
                "csesidx": "222222",
                "user_agent": "ua-2",
                "created_at": now.isoformat(),
            },
            {
                "email": "account3@example.com",
                "team_id": "team-3",
                "secure_c_ses": "ses-3",
                "host_c_oses": "oses-3",
                "csesidx": "333333",
                "user_agent": "ua-3",
                "created_at": now.isoformat(),
            },
        ],
        "settings": {
            "account_expiry_days": 30,
            "expiry_warning_days": 3,
        },
    }


@pytest.fixture
def temp_config_file(valid_config_data):
    """创建临时配置文件"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as f:
        json.dump(valid_config_data, f)
        temp_path = f.name

    yield temp_path

    # 清理
    Path(temp_path).unlink(missing_ok=True)


class TestConfigLoaderAccountPoolIntegration:
    """测试配置加载器与账号池的集成"""

    def test_load_and_initialize_pool(self, temp_config_file):
        """测试从配置文件加载并初始化账号池"""
        # 加载配置
        config_loader = ConfigLoader(temp_config_file)
        accounts = config_loader.load_accounts()

        # 初始化账号池
        pool = AccountPool()
        for account in accounts:
            pool.add_account(account)

        # 验证
        assert len(pool.accounts) == 3
        assert pool.get_pool_status()["total"] == 3
        assert pool.get_pool_status()["active"] == 3

    def test_pool_with_mixed_account_states(self, temp_config_file):
        """测试包含不同状态账号的池"""
        config_loader = ConfigLoader(temp_config_file)
        accounts = config_loader.load_accounts()

        pool = AccountPool()
        for account in accounts:
            pool.add_account(account)

        # 设置不同状态
        accounts[0].set_cooldown(3600, AccountStatus.COOLDOWN_401)  # 冷却中
        accounts[2].status = AccountStatus.ERROR  # 错误状态

        # 验证池状态
        status = pool.get_pool_status()
        assert status["total"] == 3
        assert status["active"] == 1  # 只有 account[1] 可用
        assert status["cooldown"] == 1


class TestAccountPoolRoundRobinIntegration:
    """测试账号池轮询集成"""

    @pytest.mark.asyncio
    async def test_round_robin_with_multiple_accounts(self, temp_config_file):
        """测试多账号轮询"""
        config_loader = ConfigLoader(temp_config_file)
        accounts = config_loader.load_accounts()

        pool = AccountPool()
        for account in accounts:
            pool.add_account(account)

        # 获取账号多次，验证轮询
        selected_accounts = []
        for _ in range(6):
            account = await pool.get_available_account()
            selected_accounts.append(account.email)

        # 验证轮询模式：account1, account2, account3, account1, account2, account3
        assert selected_accounts[0] == "account1@example.com"
        assert selected_accounts[1] == "account2@example.com"
        assert selected_accounts[2] == "account3@example.com"
        assert selected_accounts[3] == "account1@example.com"
        assert selected_accounts[4] == "account2@example.com"
        assert selected_accounts[5] == "account3@example.com"

    @pytest.mark.asyncio
    async def test_skip_cooldown_in_rotation(self, temp_config_file):
        """测试轮询时跳过冷却账号"""
        config_loader = ConfigLoader(temp_config_file)
        accounts = config_loader.load_accounts()

        pool = AccountPool()
        for account in accounts:
            pool.add_account(account)

        # 将第二个账号设置为冷却
        pool.accounts[1].set_cooldown(3600, AccountStatus.COOLDOWN_429)

        # 获取账号多次
        selected_accounts = []
        for _ in range(4):
            account = await pool.get_available_account()
            selected_accounts.append(account.email)

        # 应该跳过 account2，只在 account1 和 account3 之间轮询
        assert "account2@example.com" not in selected_accounts
        assert selected_accounts.count("account1@example.com") == 2
        assert selected_accounts.count("account3@example.com") == 2


class TestTokenManagerAccountIntegration:
    """测试 Token 管理器与账号的集成"""

    @pytest.mark.asyncio
    async def test_token_manager_initialization_with_account(
        self, temp_config_file
    ):
        """测试账号的 Token 管理器初始化"""
        config_loader = ConfigLoader(temp_config_file)
        accounts = config_loader.load_accounts()

        account = accounts[0]

        # 验证 TokenManager 已初始化
        assert account.token_manager is not None
        assert account.token_manager.team_id == account.team_id
        assert account.token_manager.secure_c_ses == account.secure_c_ses

    @pytest.mark.asyncio
    async def test_multiple_accounts_independent_tokens(self, temp_config_file):
        """测试多个账号的 Token 管理器独立性"""
        config_loader = ConfigLoader(temp_config_file)
        accounts = config_loader.load_accounts()

        # 每个账号应该有独立的 TokenManager
        token_managers = [acc.token_manager for acc in accounts]

        # 验证是不同的实例
        assert token_managers[0] is not token_managers[1]
        assert token_managers[1] is not token_managers[2]

        # 验证每个 TokenManager 有正确的 team_id
        assert token_managers[0].team_id == "team-1"
        assert token_managers[1].team_id == "team-2"
        assert token_managers[2].team_id == "team-3"


class TestAccountPoolErrorHandlingIntegration:
    """测试账号池错误处理集成"""

    def test_handle_401_error_integration(self, temp_config_file):
        """测试 401 错误的完整处理流程"""
        config_loader = ConfigLoader(temp_config_file)
        accounts = config_loader.load_accounts()

        pool = AccountPool()
        for account in accounts:
            pool.add_account(account)

        account = pool.accounts[0]
        initial_error_count = account.error_count

        # 触发 401 错误处理
        pool.handle_error(account, 401, "Unauthorized")

        # 验证状态变化
        assert account.status == AccountStatus.COOLDOWN_401
        assert account.is_in_cooldown() is True
        assert account.error_count == initial_error_count + 1
        assert account.is_available() is False

    def test_handle_429_error_integration(self, temp_config_file):
        """测试 429 错误的完整处理流程"""
        config_loader = ConfigLoader(temp_config_file)
        accounts = config_loader.load_accounts()

        pool = AccountPool()
        for account in accounts:
            pool.add_account(account)

        account = pool.accounts[0]

        # 触发 429 错误处理
        pool.handle_error(account, 429, "Rate limit exceeded")

        # 验证状态变化
        assert account.status == AccountStatus.COOLDOWN_429
        assert account.is_in_cooldown() is True

    def test_multiple_errors_mark_as_error(self, temp_config_file):
        """测试多次错误后标记为 ERROR 状态"""
        config_loader = ConfigLoader(temp_config_file)
        accounts = config_loader.load_accounts()

        pool = AccountPool()
        for account in accounts:
            pool.add_account(account)

        account = pool.accounts[0]

        # 触发 5 次错误
        for i in range(5):
            pool.handle_error(account, 500, f"Server error {i}")

        # 验证账号被标记为 ERROR
        assert account.status == AccountStatus.ERROR
        assert account.error_count == 5


class TestAccountLifecycleIntegration:
    """测试账号生命周期集成"""

    def test_cleanup_expired_accounts(self):
        """测试清理过期账号的完整流程"""
        now = datetime.now(timezone.utc)
        expired_date = now - timedelta(days=31)

        # 创建包含过期账号的配置
        config_data = {
            "accounts": [
                {
                    "email": "fresh@example.com",
                    "team_id": "team-1",
                    "secure_c_ses": "ses-1",
                    "host_c_oses": "oses-1",
                    "csesidx": "111111",
                    "user_agent": "ua-1",
                    "created_at": now.isoformat(),
                },
                {
                    "email": "expired@example.com",
                    "team_id": "team-2",
                    "secure_c_ses": "ses-2",
                    "host_c_oses": "oses-2",
                    "csesidx": "222222",
                    "user_agent": "ua-2",
                    "created_at": expired_date.isoformat(),
                },
            ]
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(config_data, f)
            temp_path = f.name

        try:
            config_loader = ConfigLoader(temp_path)
            accounts = config_loader.load_accounts()

            pool = AccountPool()
            for account in accounts:
                pool.add_account(account)

            # 清理过期账号
            removed_count = pool.cleanup_expired_accounts()

            # 验证
            assert removed_count == 1
            assert len(pool.accounts) == 1
            assert pool.accounts[0].email == "fresh@example.com"

        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_warn_expiring_accounts(self):
        """测试即将过期账号警告"""
        now = datetime.now(timezone.utc)
        expiring_date = now - timedelta(days=28)  # 剩余 2 天

        config_data = {
            "accounts": [
                {
                    "email": "expiring@example.com",
                    "team_id": "team-1",
                    "secure_c_ses": "ses-1",
                    "host_c_oses": "oses-1",
                    "csesidx": "111111",
                    "user_agent": "ua-1",
                    "created_at": expiring_date.isoformat(),
                }
            ]
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(config_data, f)
            temp_path = f.name

        try:
            config_loader = ConfigLoader(temp_path)
            accounts = config_loader.load_accounts()

            pool = AccountPool()
            for account in accounts:
                pool.add_account(account)

            # 检查即将过期的账号
            expiring_accounts = pool.warn_expiring_accounts()

            # 验证
            assert len(expiring_accounts) == 1
            assert expiring_accounts[0].email == "expiring@example.com"

        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestConcurrentAccessIntegration:
    """测试并发访问集成"""

    @pytest.mark.asyncio
    async def test_concurrent_account_access(self, temp_config_file):
        """测试并发获取账号"""
        config_loader = ConfigLoader(temp_config_file)
        accounts = config_loader.load_accounts()

        pool = AccountPool()
        for account in accounts:
            pool.add_account(account)

        # 并发获取账号
        async def get_account():
            return await pool.get_available_account()

        tasks = [get_account() for _ in range(10)]
        results = await asyncio.gather(*tasks)

        # 验证所有请求都成功
        assert len(results) == 10
        assert all(isinstance(r, Account) for r in results)

        # 验证轮询分布
        emails = [r.email for r in results]
        assert emails.count("account1@example.com") >= 3
        assert emails.count("account2@example.com") >= 3
        assert emails.count("account3@example.com") >= 3
