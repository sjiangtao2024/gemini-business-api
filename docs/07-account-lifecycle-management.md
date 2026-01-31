# 账号生命周期管理文档

> 版本：v1.0
> 日期：2025-01-31

## 📋 概述

Gemini Business 提供30天免费试用期，本文档详细说明账号从注册到过期的完整生命周期管理策略。

**核心特性：**
- ✅ 30天试用期自动检测
- ✅ 过期预警机制（剩余<3天）
- ✅ 自动清理过期账号
- ✅ 2925邮箱自动注册（可选）
- ✅ 手动/自动账号轮换

---

## 🔄 账号生命周期

### 完整时间线

```
Day 0: 注册账号
  │
  ├─ 获取 Cookie（__Secure-c-SES, __Host-c-OSES, csesidx）
  ├─ 记录 created_at 时间戳
  └─ 添加到账号池

Day 1-27: 正常使用期
  │
  ├─ Token 每5分钟自动刷新（本地生成JWT）
  ├─ Cookie 持续有效
  ├─ 账号状态: active
  └─ 可用邮箱验证码重新登录

Day 28: 第一次预警
  │
  ├─ 剩余天数 < 3
  ├─ 日志输出: ⚠️ 账号即将过期（剩余2天）
  └─ 账号状态: expiring_soon

Day 29: 第二次预警
  │
  ├─ 日志输出: ⚠️ 账号即将过期（剩余1天）
  └─ 建议: 立即准备新账号

Day 30: 试用期结束
  │
  ├─ Cookie 失效
  ├─ 账号状态: expired
  ├─ 自动从账号池移除
  └─ 需要注册新账号

Day 30+: 账号不可用
  │
  └─ 必须注册新账号继续使用
```

---

## 🔍 过期检测机制

### 检测逻辑

```python
from datetime import datetime, timezone
import time

class Account:
    def __init__(self, data: dict):
        self.email = data['email']
        self.created_at = self._parse_timestamp(data['created_at'])
        self.expires_at = self._parse_timestamp(data.get('expires_at'))

    def _parse_timestamp(self, ts_str: str) -> float:
        """解析ISO 8601时间戳为Unix时间戳"""
        if not ts_str:
            return None
        dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
        return dt.timestamp()

    def is_expired(self) -> bool:
        """检查账号是否过期"""
        current_time = time.time()

        # 方式1: 使用显式过期时间
        if self.expires_at:
            return current_time > self.expires_at

        # 方式2: 基于创建时间计算（30天）
        age_seconds = current_time - self.created_at
        age_days = age_seconds / 86400

        return age_days >= 30

    def get_remaining_days(self) -> int:
        """获取剩余天数"""
        current_time = time.time()

        if self.expires_at:
            remaining_seconds = self.expires_at - current_time
        else:
            # 30天 = 2592000秒
            age_seconds = current_time - self.created_at
            remaining_seconds = 2592000 - age_seconds

        remaining_days = remaining_seconds / 86400
        return max(0, int(remaining_days))

    def should_warn_expiry(self) -> bool:
        """是否应该警告即将过期（剩余<3天）"""
        remaining = self.get_remaining_days()
        return 0 < remaining < 3

    def get_account_age_days(self) -> int:
        """获取账号年龄（天数）"""
        age_seconds = time.time() - self.created_at
        return int(age_seconds / 86400)
```

### 状态转换

```
active (正常使用)
   ↓
   age > 27天
   ↓
expiring_soon (即将过期，剩余<3天)
   ↓
   age >= 30天
   ↓
expired (已过期)
   ↓
从账号池移除
```

---

## 🔔 预警机制

### 预警级别

| 剩余天数 | 预警级别 | 日志颜色 | 建议操作 |
|---------|---------|---------|---------|
| > 3天 | 正常 | 绿色 | 无需操作 |
| 2-3天 | 警告 | 黄色 | 准备新账号 |
| 1天 | 紧急 | 橙色 | 立即注册新账号 |
| 0天 | 过期 | 红色 | 账号已不可用 |

### 预警实现

```python
import logging

logger = logging.getLogger(__name__)

class AccountLifecycleManager:
    """账号生命周期管理器"""

    def __init__(self, account_pool):
        self.account_pool = account_pool

    async def check_and_warn_expiry(self):
        """检查并警告即将过期的账号"""
        for account in self.account_pool.accounts:
            if account.is_expired():
                # 已过期，标记并记录
                account.status = 'expired'
                logger.error(
                    f"❌ 账号已过期: {account.email} "
                    f"(使用了 {account.get_account_age_days()} 天)"
                )
                continue

            remaining = account.get_remaining_days()

            if remaining < 1:
                logger.error(
                    f"🔴 账号即将过期: {account.email} "
                    f"(剩余 {remaining} 天) - 请立即注册新账号！"
                )
                account.status = 'expiring_soon'

            elif remaining < 3:
                logger.warning(
                    f"⚠️ 账号即将过期: {account.email} "
                    f"(剩余 {remaining} 天) - 建议准备新账号"
                )
                account.status = 'expiring_soon'

            else:
                # 正常状态
                if account.status != 'active':
                    logger.info(
                        f"✅ 账号状态正常: {account.email} "
                        f"(剩余 {remaining} 天)"
                    )
                account.status = 'active'
```

---

## 🗑️ 自动清理

### 清理策略

```python
class AccountCleaner:
    """账号清理器"""

    def __init__(self, account_pool, backup_dir: str = "./data/expired"):
        self.account_pool = account_pool
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    async def cleanup_expired_accounts(self):
        """清理过期账号"""
        expired_accounts = []
        active_accounts = []

        for account in self.account_pool.accounts:
            if account.is_expired():
                expired_accounts.append(account)
                logger.info(f"🗑️ 移除过期账号: {account.email}")
            else:
                active_accounts.append(account)

        # 备份过期账号（用于统计）
        if expired_accounts:
            self._backup_expired_accounts(expired_accounts)

        # 更新账号池
        self.account_pool.accounts = active_accounts

        return {
            'removed_count': len(expired_accounts),
            'active_count': len(active_accounts)
        }

    def _backup_expired_accounts(self, accounts: list):
        """备份过期账号信息"""
        backup_file = self.backup_dir / f"expired_{int(time.time())}.json"

        data = [
            {
                'email': acc.email,
                'team_id': acc.team_id,
                'created_at': acc.created_at,
                'expired_at': time.time(),
                'total_days': acc.get_account_age_days()
            }
            for acc in accounts
        ]

        with open(backup_file, 'w') as f:
            json.dump(data, f, indent=2)

        logger.info(f"💾 已备份 {len(accounts)} 个过期账号到 {backup_file}")
```

---

## ⏰ 后台定时任务

### 任务调度

```python
import asyncio

class BackgroundTasks:
    """后台任务调度器"""

    def __init__(self, lifecycle_manager, cleaner):
        self.lifecycle_manager = lifecycle_manager
        self.cleaner = cleaner
        self._running = False

    async def start(self):
        """启动后台任务"""
        self._running = True

        # 启动每日检查任务
        asyncio.create_task(self._daily_check())

        logger.info("✅ 后台任务已启动")

    async def stop(self):
        """停止后台任务"""
        self._running = False
        logger.info("⏹️ 后台任务已停止")

    async def _daily_check(self):
        """每日检查任务（每天凌晨2点执行）"""
        while self._running:
            # 等待到凌晨2点
            await self._wait_until_2am()

            if not self._running:
                break

            logger.info("🔍 开始每日账号检查...")

            try:
                # 1. 检查并警告即将过期的账号
                await self.lifecycle_manager.check_and_warn_expiry()

                # 2. 清理过期账号
                result = await self.cleaner.cleanup_expired_accounts()

                logger.info(
                    f"✅ 每日检查完成: "
                    f"移除 {result['removed_count']} 个过期账号, "
                    f"剩余 {result['active_count']} 个活跃账号"
                )

            except Exception as e:
                logger.error(f"❌ 每日检查失败: {e}")

            # 等待24小时后再次执行
            await asyncio.sleep(86400)

    async def _wait_until_2am(self):
        """等待到凌晨2点"""
        now = datetime.now()
        target = now.replace(hour=2, minute=0, second=0, microsecond=0)

        # 如果已过凌晨2点，目标时间设为明天
        if now > target:
            target += timedelta(days=1)

        wait_seconds = (target - now).total_seconds()
        await asyncio.sleep(wait_seconds)
```

---

## 🤖 自动账号注册（可选）

### 2925邮箱集成

```python
import imaplib
import email
import re
from typing import Optional

class Mail2925Handler:
    """2925邮箱验证码获取器"""

    def __init__(self, email_address: str, password: str):
        self.email_address = email_address  # sjiangtao@2925.com
        self.password = password
        self.imap_host = "imap.2925.com"
        self.imap_port = 993

    def get_verification_code(self,
                             target_email: str,  # xxx@goodcv.fun
                             timeout: int = 300) -> str:
        """
        从2925邮箱获取Google验证码

        参数:
            target_email: 注册使用的邮箱（goodcv.fun）
            timeout: 超时时间（秒）

        返回:
            6位验证码
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                # 连接IMAP服务器
                mail = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
                mail.login(self.email_address, self.password)
                mail.select('INBOX')

                # 搜索来自Google的未读邮件
                status, messages = mail.search(None, 'UNSEEN FROM "google.com"')

                if status == 'OK' and messages[0]:
                    email_ids = messages[0].split()

                    # 从最新邮件开始检查
                    for email_id in reversed(email_ids):
                        status, msg_data = mail.fetch(email_id, '(RFC822)')

                        if status == 'OK':
                            raw_email = msg_data[0][1]
                            msg = email.message_from_bytes(raw_email)

                            # 检查收件人是否匹配
                            to_header = msg.get('To', '')
                            if target_email in to_header:
                                code = self._extract_code(msg)
                                if code:
                                    mail.close()
                                    mail.logout()
                                    return code

                mail.close()
                mail.logout()

            except Exception as e:
                logger.warning(f"邮箱检查失败: {e}")

            time.sleep(5)

        raise TimeoutError(f"等待验证码超时（{timeout}秒）")

    def _extract_code(self, msg) -> Optional[str]:
        """从邮件中提取验证码"""
        body = self._get_email_body(msg)
        if not body:
            return None

        patterns = [
            r'verification code is[:\s]+([A-Z0-9]{6})',
            r'验证码[：:\s]+([A-Z0-9]{6})',
            r'([A-Z0-9]{6})\s+is your verification code',
        ]

        for pattern in patterns:
            match = re.search(pattern, body, re.IGNORECASE)
            if match:
                return match.group(1)

        return None
```

### Playwright 自动注册

```python
from playwright.async_api import async_playwright

class GeminiAutoRegister:
    """Gemini Business 自动注册"""

    def __init__(self, mail_handler: Mail2925Handler):
        self.mail_handler = mail_handler

    async def register_account(self, target_email: str) -> dict:
        """
        自动注册账号

        参数:
            target_email: xxx@goodcv.fun

        返回:
            账号配置（email, team_id, cookies等）
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context()
            page = await context.new_page()

            try:
                # 1. 访问注册页面
                await page.goto("https://gemini.google.com/business/signup")
                await page.wait_for_load_state('networkidle')

                # 2. 输入邮箱
                await page.fill('input[type="email"]', target_email)
                await page.click('button:has-text("Continue")')
                await page.wait_for_timeout(3000)

                # 3. 获取验证码
                verification_code = self.mail_handler.get_verification_code(
                    target_email,
                    timeout=300
                )

                # 4. 输入验证码
                await page.fill('input[name="code"]', verification_code)
                await page.click('button:has-text("Verify")')
                await page.wait_for_load_state('networkidle')

                # 5. 等待跳转
                await page.wait_for_url('**/business/**', timeout=10000)

                # 6. 提取数据
                cookies = await context.cookies()
                cookie_dict = {c['name']: c['value'] for c in cookies}

                account_data = {
                    'email': target_email,
                    'team_id': await self._extract_team_id(page),
                    'secure_c_ses': cookie_dict.get('__Secure-c-SES', ''),
                    'host_c_oses': cookie_dict.get('__Host-c-OSES', ''),
                    'csesidx': cookie_dict.get('csesidx', ''),
                    'user_agent': await page.evaluate('navigator.userAgent'),
                    'created_at': datetime.now(timezone.utc).isoformat(),
                    'expires_at': (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
                }

                return account_data

            finally:
                await browser.close()
```

### 自动轮换策略

```python
class AutoRotationStrategy:
    """自动账号轮换策略"""

    def __init__(self, account_pool, auto_register, min_accounts: int = 3):
        self.account_pool = account_pool
        self.auto_register = auto_register
        self.min_accounts = min_accounts

    async def maintain_account_pool(self):
        """维护账号池（自动补充）"""
        # 统计可用账号
        active_count = len([
            acc for acc in self.account_pool.accounts
            if not acc.is_expired() and acc.get_remaining_days() > 3
        ])

        # 需要补充的数量
        needed = max(0, self.min_accounts - active_count)

        if needed > 0:
            logger.info(f"🔄 账号数量不足，需要补充 {needed} 个新账号")

            for i in range(needed):
                try:
                    email = f"gemini{int(time.time())}@goodcv.fun"
                    account = await self.auto_register.register_account(email)

                    # 添加到账号池
                    await self.account_pool.add_account(account)

                    logger.info(f"✅ 成功注册并添加账号 {i+1}/{needed}: {email}")

                    # 避免频率限制
                    await asyncio.sleep(10)

                except Exception as e:
                    logger.error(f"❌ 账号注册失败: {e}")
```

---

## 📊 统计和监控

### 账号统计API

```python
@app.get("/admin/account-stats")
async def get_account_stats():
    """获取账号统计信息"""
    accounts = account_pool.accounts

    total = len(accounts)
    active = len([a for a in accounts if a.status == 'active'])
    expiring_soon = len([a for a in accounts if a.should_warn_expiry()])
    expired = len([a for a in accounts if a.is_expired()])

    # 平均账号年龄
    avg_age = sum(a.get_account_age_days() for a in accounts) / total if total > 0 else 0

    # 即将过期的账号详情
    expiring_details = [
        {
            'email': a.email,
            'remaining_days': a.get_remaining_days(),
            'age_days': a.get_account_age_days()
        }
        for a in accounts if a.should_warn_expiry()
    ]

    return {
        'summary': {
            'total': total,
            'active': active,
            'expiring_soon': expiring_soon,
            'expired': expired,
            'average_age_days': round(avg_age, 1)
        },
        'expiring_accounts': expiring_details,
        'health_status': 'healthy' if active >= 2 else 'warning'
    }
```

---

## 🎯 最佳实践

### 推荐配置

**个人使用（手动管理）：**
```json
{
  "settings": {
    "account_expiry_days": 30,
    "expiry_warning_days": 3,
    "auto_rotate_enabled": false,
    "min_accounts": 2
  }
}
```

**自动化场景：**
```json
{
  "settings": {
    "account_expiry_days": 30,
    "expiry_warning_days": 5,
    "auto_rotate_enabled": true,
    "min_accounts": 5
  }
}
```

### 运维建议

1. **每天检查日志**
   ```bash
   docker-compose logs | grep "即将过期"
   ```

2. **提前准备账号**
   - 剩余5天时开始准备
   - 至少保持2-3个可用账号

3. **定期备份配置**
   ```bash
   cp config/accounts.json config/accounts_backup_$(date +%Y%m%d).json
   ```

4. **监控账号池状态**
   ```bash
   curl http://localhost:8000/admin/account-stats
   ```

---

## 📝 配置示例

### 手动管理账号

```json
{
  "accounts": [
    {
      "email": "gemini1@goodcv.fun",
      "team_id": "xxx-xxx-xxx",
      "secure_c_ses": "CSE.xxx",
      "host_c_oses": "COS.xxx",
      "csesidx": "123456",
      "user_agent": "Mozilla/5.0...",
      "created_at": "2025-01-31T10:00:00Z",
      "expires_at": "2025-03-02T10:00:00Z"
    },
    {
      "email": "gemini2@goodcv.fun",
      "team_id": "yyy-yyy-yyy",
      "secure_c_ses": "CSE.yyy",
      "host_c_oses": "COS.yyy",
      "csesidx": "123457",
      "user_agent": "Mozilla/5.0...",
      "created_at": "2025-02-05T10:00:00Z"
    }
  ],
  "settings": {
    "account_expiry_days": 30,
    "expiry_warning_days": 3,
    "auto_rotate_enabled": false
  }
}
```

---

## ✅ 检查清单

### 部署前检查
- [ ] 已设置 `account_expiry_days = 30`
- [ ] 已设置 `expiry_warning_days = 3`
- [ ] 所有账号都有 `created_at` 字段
- [ ] 后台任务已启动

### 日常运维
- [ ] 每天检查日志中的过期警告
- [ ] 剩余<5天时准备新账号
- [ ] 定期查看账号池统计（/admin/account-stats）
- [ ] 每周备份配置文件

### 自动化（可选）
- [ ] 配置2925邮箱凭据
- [ ] 测试自动注册流程
- [ ] 设置 `auto_rotate_enabled = true`
- [ ] 设置 `min_accounts` 最小账号数

---

**文档版本历史：**
- v1.0 (2025-01-31): 初始版本，完成30天账号生命周期管理设计
