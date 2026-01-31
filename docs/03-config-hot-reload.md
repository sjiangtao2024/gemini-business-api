# 配置热重载机制设计文档

> 版本：v1.0
> 日期：2025-01-31

## 📋 概述

设计一个高效、可靠的配置热重载机制，支持账号配置的动态更新，无需重启服务。

**核心目标：**
- ✅ 监听 `config/accounts.json` 文件变化
- ✅ 自动重新加载配置
- ✅ 保留现有账号的运行时状态（Token、冷却状态）
- ✅ 平滑切换，不中断正在进行的请求
- ✅ 错误配置回滚保护

---

## 🎯 使用场景

### 场景 1：添加新账号
用户编辑 `config/accounts.json` 添加新账号，服务自动加载新账号到账号池。

### 场景 2：移除账号
用户从配置文件中删除某个账号，服务自动将其从账号池移除。

### 场景 3：修改账号信息
用户更新账号的 Cookie 信息（如 Token 过期后手动更新），服务自动重新加载。

### 场景 4：修改全局设置
用户调整冷却时间、刷新间隔等参数，服务自动应用新配置。

### 场景 5：错误配置保护
用户编辑配置文件时写入了错误的 JSON 格式，服务应拒绝加载并保持当前配置。

---

## 🏗️ 技术方案

### 方案选型

| 方案 | 优点 | 缺点 | 适用场景 |
|------|------|------|---------|
| **watchdog** | 跨平台，API 简单 | 需要额外依赖 | ✅ 推荐（树莓派5支持） |
| **watchfiles** | 性能高，基于 Rust | 需要编译环境 | 生产环境（性能优先） |
| **polling** | 无依赖，兼容性好 | 延迟高，资源消耗大 | 备用方案 |

**推荐方案：watchdog**
- 树莓派5完全支持
- API 简单易用
- 社区活跃，文档完善

---

## 📦 核心组件设计

### 1. ConfigWatcher（配置监听器）

```python
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import asyncio
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class ConfigFileHandler(FileSystemEventHandler):
    """配置文件变化处理器"""

    def __init__(self, config_path: Path, reload_callback):
        self.config_path = config_path
        self.reload_callback = reload_callback
        self.last_modified = 0
        self._lock = asyncio.Lock()

    def on_modified(self, event):
        """文件修改事件"""
        if event.src_path != str(self.config_path):
            return

        # 防止重复触发（某些编辑器会触发多次事件）
        current_time = time.time()
        if current_time - self.last_modified < 1.0:
            return

        self.last_modified = current_time

        logger.info(f"[CONFIG] 检测到配置文件变化: {self.config_path.name}")

        # 异步调用重载回调
        asyncio.create_task(self._safe_reload())

    async def _safe_reload(self):
        """安全重载（带锁保护）"""
        async with self._lock:
            try:
                await self.reload_callback()
            except Exception as e:
                logger.error(f"[CONFIG] 重载失败: {e}")


class ConfigWatcher:
    """配置文件监听器"""

    def __init__(self, config_path: Path, reload_callback):
        self.config_path = config_path
        self.reload_callback = reload_callback
        self.observer = None
        self.event_handler = None

    def start(self):
        """启动监听"""
        self.event_handler = ConfigFileHandler(
            self.config_path,
            self.reload_callback
        )

        self.observer = Observer()
        self.observer.schedule(
            self.event_handler,
            path=str(self.config_path.parent),
            recursive=False
        )
        self.observer.start()

        logger.info(f"[CONFIG] 配置文件监听已启动: {self.config_path}")

    def stop(self):
        """停止监听"""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            logger.info("[CONFIG] 配置文件监听已停止")
```

### 2. ConfigLoader（配置加载器）

```python
class ConfigLoader:
    """配置加载器（支持验证和回滚）"""

    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.current_config = None
        self.backup_config = None

    async def load(self) -> dict:
        """加载配置（带验证）"""
        try:
            # 1. 读取文件
            with open(self.config_path, 'r', encoding='utf-8') as f:
                raw_data = f.read()

            # 2. 解析 JSON
            config_data = json.loads(raw_data)

            # 3. 验证配置格式
            self._validate_config(config_data)

            # 4. 备份当前配置
            if self.current_config is not None:
                self.backup_config = self.current_config

            # 5. 更新当前配置
            self.current_config = config_data

            logger.info(f"[CONFIG] 配置加载成功，共 {len(config_data['accounts'])} 个账号")
            return config_data

        except json.JSONDecodeError as e:
            logger.error(f"[CONFIG] JSON 格式错误: {e}")
            raise ValueError(f"配置文件 JSON 格式错误: {e}")

        except Exception as e:
            logger.error(f"[CONFIG] 配置加载失败: {e}")
            raise

    def _validate_config(self, config: dict):
        """验证配置格式"""
        # 1. 必须包含 accounts 字段
        if "accounts" not in config:
            raise ValueError("配置缺少 'accounts' 字段")

        if not isinstance(config["accounts"], list):
            raise ValueError("'accounts' 必须是数组")

        # 2. 验证每个账号的必填字段
        required_fields = ["team_id", "secure_c_ses", "csesidx", "user_agent"]

        for i, account in enumerate(config["accounts"]):
            for field in required_fields:
                if field not in account:
                    raise ValueError(f"账号 {i+1} 缺少必填字段: {field}")

            # 验证字段类型
            if not isinstance(account["team_id"], str):
                raise ValueError(f"账号 {i+1} 的 team_id 必须是字符串")

        # 3. 验证 settings（可选）
        if "settings" in config:
            settings = config["settings"]

            # 验证数值范围
            if "token_refresh_interval_hours" in settings:
                value = settings["token_refresh_interval_hours"]
                if not (1 <= value <= 12):
                    raise ValueError("token_refresh_interval_hours 必须在 1-12 小时之间")

            if "check_interval_minutes" in settings:
                value = settings["check_interval_minutes"]
                if not (1 <= value <= 120):
                    raise ValueError("check_interval_minutes 必须在 1-120 分钟之间")

        logger.debug("[CONFIG] 配置验证通过")

    def rollback(self):
        """回滚到备份配置"""
        if self.backup_config is None:
            raise RuntimeError("没有可用的备份配置")

        logger.warning("[CONFIG] 回滚到上一次有效配置")
        self.current_config = self.backup_config
        return self.current_config
```

### 3. AccountPool 集成热重载

```python
class AccountPool:
    """账号池（支持热重载）"""

    def __init__(self, config_loader: ConfigLoader):
        self.config_loader = config_loader
        self.accounts = {}  # {team_id: AccountInstance}
        self.reload_lock = asyncio.Lock()

    async def reload(self):
        """重新加载配置（保留运行时状态）"""
        async with self.reload_lock:
            try:
                # 1. 加载新配置
                new_config = await self.config_loader.load()
                new_accounts_data = new_config["accounts"]

                # 2. 构建新账号 ID 集合
                new_account_ids = {acc["team_id"] for acc in new_accounts_data}
                old_account_ids = set(self.accounts.keys())

                # 3. 识别变化
                added_ids = new_account_ids - old_account_ids
                removed_ids = old_account_ids - new_account_ids
                updated_ids = new_account_ids & old_account_ids

                logger.info(
                    f"[CONFIG] 配置变化: "
                    f"新增 {len(added_ids)}, "
                    f"移除 {len(removed_ids)}, "
                    f"保留 {len(updated_ids)}"
                )

                # 4. 添加新账号
                for account_data in new_accounts_data:
                    team_id = account_data["team_id"]

                    if team_id in added_ids:
                        # 创建新账号实例
                        self.accounts[team_id] = await self._create_account(account_data)
                        logger.info(f"[CONFIG] 新增账号: {team_id[:8]}...")

                    elif team_id in updated_ids:
                        # 更新现有账号配置（保留运行时状态）
                        await self._update_account(team_id, account_data)
                        logger.info(f"[CONFIG] 更新账号: {team_id[:8]}...")

                # 5. 移除已删除的账号
                for team_id in removed_ids:
                    await self._remove_account(team_id)
                    logger.info(f"[CONFIG] 移除账号: {team_id[:8]}...")

                # 6. 更新全局设置
                if "settings" in new_config:
                    await self._update_settings(new_config["settings"])

                logger.info("[CONFIG] ✅ 配置重载完成")

            except Exception as e:
                logger.error(f"[CONFIG] ❌ 配置重载失败: {e}")
                # 可选：尝试回滚
                # self.config_loader.rollback()
                raise

    async def _create_account(self, account_data: dict):
        """创建新账号实例"""
        account = Account(
            team_id=account_data["team_id"],
            cookies={
                "secure_c_ses": account_data["secure_c_ses"],
                "host_c_oses": account_data.get("host_c_oses", ""),
                "csesidx": account_data["csesidx"],
            },
            user_agent=account_data["user_agent"]
        )

        # 初始化 Token Manager
        account.token_manager = TokenManager(account)

        # 预热：提前获取 Token
        try:
            await account.token_manager.get_token()
        except Exception as e:
            logger.warning(f"[CONFIG] 账号 {account.team_id[:8]} 预热失败: {e}")

        return account

    async def _update_account(self, team_id: str, new_data: dict):
        """更新账号配置（保留运行时状态）"""
        account = self.accounts[team_id]

        # 保留的运行时状态
        old_token = account.token_manager.jwt_token
        old_expires_at = account.token_manager.token_expires_at
        old_status = account.status
        old_cooldown_until = account.cooldown_until

        # 更新配置
        account.cookies = {
            "secure_c_ses": new_data["secure_c_ses"],
            "host_c_oses": new_data.get("host_c_oses", ""),
            "csesidx": new_data["csesidx"],
        }
        account.user_agent = new_data["user_agent"]

        # 检查 Cookie 是否变化
        cookies_changed = (
            account.cookies["secure_c_ses"] != new_data["secure_c_ses"] or
            account.cookies["csesidx"] != new_data["csesidx"]
        )

        if cookies_changed:
            # Cookie 变化，清除旧 Token，强制重新获取
            account.token_manager.jwt_token = None
            account.token_manager.token_expires_at = None
            logger.info(f"[CONFIG] 账号 {team_id[:8]} Cookie 已更新，将重新获取 Token")
        else:
            # Cookie 未变化，保留 Token
            account.token_manager.jwt_token = old_token
            account.token_manager.token_expires_at = old_expires_at
            logger.debug(f"[CONFIG] 账号 {team_id[:8]} 配置未变化，保留运行时状态")

        # 保留状态
        account.status = old_status
        account.cooldown_until = old_cooldown_until

    async def _remove_account(self, team_id: str):
        """移除账号"""
        if team_id in self.accounts:
            # 可选：优雅关闭（等待正在进行的请求完成）
            account = self.accounts[team_id]
            # await account.shutdown()

            del self.accounts[team_id]

    async def _update_settings(self, settings: dict):
        """更新全局设置"""
        if "token_refresh_interval_hours" in settings:
            # 更新 Token 刷新间隔
            pass

        if "cooldown_401_seconds" in settings:
            # 更新冷却时间
            pass

        logger.info("[CONFIG] 全局设置已更新")
```

---

## 🔄 热重载流程

### 完整流程图

```
用户编辑 accounts.json
    ↓
watchdog 检测到文件变化
    ↓
触发 on_modified 事件
    ↓
防抖处理（1秒内只触发一次）
    ↓
加载新配置（ConfigLoader.load）
    ↓
验证 JSON 格式 → 失败？ → 拒绝加载，保持当前配置
    ↓ 成功
验证必填字段 → 失败？ → 拒绝加载，记录错误
    ↓ 成功
对比新旧配置
    ↓
识别变化（新增/移除/更新）
    ↓
执行变更（AccountPool.reload）
    ├─ 新增账号 → 创建实例 → 预热 Token
    ├─ 移除账号 → 优雅关闭 → 删除实例
    └─ 更新账号 → Cookie变化？
                    ├─ 是 → 清除 Token，强制刷新
                    └─ 否 → 保留运行时状态
    ↓
应用新配置
    ↓
记录变更日志
    ↓
重载完成 ✅
```

### 关键设计点

#### 1. 防抖处理
某些编辑器（如 Vim）保存文件时会触发多次 `modified` 事件，需要防抖：

```python
# 1秒内只触发一次
if current_time - self.last_modified < 1.0:
    return
```

#### 2. 验证优先
加载配置前必须验证，避免错误配置导致服务异常：

```python
# 先验证，后应用
config_data = json.loads(raw_data)
self._validate_config(config_data)  # 验证失败会抛出异常
self.current_config = config_data   # 验证通过才更新
```

#### 3. 状态保留
重载时保留账号的运行时状态（Token、冷却状态），避免不必要的重复刷新：

```python
# 保留的状态
old_token = account.token_manager.jwt_token
old_expires_at = account.token_manager.token_expires_at
old_cooldown_until = account.cooldown_until

# 更新配置后恢复
account.token_manager.jwt_token = old_token
```

#### 4. 并发保护
使用锁保护重载过程，避免并发重载导致状态混乱：

```python
async with self.reload_lock:
    # 重载逻辑
    pass
```

#### 5. 请求平滑切换
重载期间不中断正在进行的请求：

- 移除账号时，等待该账号的请求完成（可选）
- 新增账号时，逐步加入轮询池
- 更新账号时，保持可用状态

---

## 🛡️ 错误处理

### 错误类型

| 错误类型 | 处理策略 | 用户影响 |
|---------|---------|---------|
| JSON 格式错误 | 拒绝加载，保持当前配置 | 配置文件错误，需修复 |
| 必填字段缺失 | 拒绝加载，记录错误 | 配置文件错误，需修复 |
| 文件不存在 | 使用默认配置（空账号池） | 服务启动但无可用账号 |
| Token 获取失败 | 标记账号为不可用 | 该账号暂时不可用 |
| 并发重载冲突 | 等待锁释放后重试 | 自动处理，无影响 |

### 错误日志示例

```
[CONFIG] ❌ JSON 格式错误: Expecting ',' delimiter: line 5 column 3 (char 102)
[CONFIG] ❌ 配置验证失败: 账号 2 缺少必填字段: team_id
[CONFIG] ⚠️ 账号 1d468dcc 预热失败: 401 Unauthorized
[CONFIG] ✅ 配置重载完成，共 5 个账号
```

---

## 📊 性能优化

### 1. 懒加载策略
新增账号时，不立即获取 Token，而是在首次使用时获取：

```python
# 预热（可选）
try:
    await account.token_manager.get_token()
except Exception as e:
    logger.warning(f"预热失败: {e}")
    # 不影响账号添加，首次使用时会自动获取
```

### 2. 批量更新优化
如果用户同时修改多个账号，使用批量更新：

```python
# 批量创建账号实例
await asyncio.gather(*[
    self._create_account(acc)
    for acc in new_accounts_data
    if acc["team_id"] in added_ids
])
```

### 3. 内存占用控制
- 只保留一份备份配置（用于回滚）
- 移除账号时及时释放资源
- 定期清理无效的 Session

---

## 🔧 配置示例

### 1. 初始配置
```json
{
  "accounts": [
    {
      "team_id": "1d468dcc-11a5-4adc-8b68-8098e227000c",
      "secure_c_ses": "CSE.AXUaAj95JjqSSOJpFb2...",
      "host_c_oses": "COS.AfQtEyDX9akUCVLcm_k036...",
      "csesidx": "206226908",
      "user_agent": "Mozilla/5.0..."
    }
  ],
  "settings": {
    "token_refresh_interval_hours": 11,
    "account_expire_warning_days": 28,
    "check_interval_minutes": 30
  }
}
```

### 2. 添加新账号（热重载触发）
```json
{
  "accounts": [
    {
      "team_id": "1d468dcc-11a5-4adc-8b68-8098e227000c",
      "secure_c_ses": "CSE.AXUaAj95JjqSSOJpFb2...",
      "host_c_oses": "COS.AfQtEyDX9akUCVLcm_k036...",
      "csesidx": "206226908",
      "user_agent": "Mozilla/5.0..."
    },
    {
      "team_id": "2e579edd-22b6-5bdc-9c79-9109f338111d",
      "secure_c_ses": "CSE.NewAccount...",
      "host_c_oses": "COS.NewAccount...",
      "csesidx": "206226909",
      "user_agent": "Mozilla/5.0..."
    }
  ]
}
```

**日志输出：**
```
[CONFIG] 检测到配置文件变化: accounts.json
[CONFIG] 配置加载成功，共 2 个账号
[CONFIG] 配置变化: 新增 1, 移除 0, 保留 1
[CONFIG] 新增账号: 2e579edd...
[CONFIG] ✅ 配置重载完成
```

### 3. 更新账号 Cookie（Token 过期）
```json
{
  "accounts": [
    {
      "team_id": "1d468dcc-11a5-4adc-8b68-8098e227000c",
      "secure_c_ses": "CSE.UpdatedCookie...",  // 修改
      "host_c_oses": "COS.UpdatedCookie...",   // 修改
      "csesidx": "206226910",                   // 修改
      "user_agent": "Mozilla/5.0..."
    }
  ]
}
```

**日志输出：**
```
[CONFIG] 检测到配置文件变化: accounts.json
[CONFIG] 配置加载成功，共 1 个账号
[CONFIG] 配置变化: 新增 0, 移除 0, 保留 1
[CONFIG] 更新账号: 1d468dcc...
[CONFIG] 账号 1d468dcc Cookie 已更新，将重新获取 Token
[CONFIG] ✅ 配置重载完成
```

---

## 🧪 测试场景

### 1. 基础功能测试
- ✅ 启动时加载配置
- ✅ 文件修改触发重载
- ✅ 添加账号成功
- ✅ 移除账号成功
- ✅ 更新账号成功

### 2. 错误处理测试
- ✅ JSON 格式错误（拒绝加载）
- ✅ 缺少必填字段（拒绝加载）
- ✅ 数值超出范围（拒绝加载）
- ✅ 文件不存在（使用默认配置）

### 3. 并发测试
- ✅ 快速连续修改文件（防抖）
- ✅ 重载期间接收新请求（不阻塞）
- ✅ 并发重载请求（锁保护）

### 4. 状态保留测试
- ✅ 更新账号保留 Token
- ✅ 更新账号保留冷却状态
- ✅ Cookie 变化清除 Token

---

## 📝 使用文档

### 如何手动重载配置？

**方法 1：编辑配置文件**
```bash
# 编辑配置文件
nano config/accounts.json

# 保存后自动重载（无需重启服务）
```

**方法 2：通过 API 触发（可选扩展）**
```bash
# 可以扩展一个 API 端点触发重载
curl -X POST http://localhost:8000/admin/reload \
  -H "Authorization: Bearer admin_key"
```

### 如何验证重载成功？

**查看日志：**
```bash
docker logs -f gemini-api | grep CONFIG

# 输出示例
[CONFIG] 检测到配置文件变化: accounts.json
[CONFIG] 配置加载成功，共 3 个账号
[CONFIG] 配置变化: 新增 1, 移除 0, 保留 2
[CONFIG] 新增账号: 2e579edd...
[CONFIG] ✅ 配置重载完成
```

**查看账号池状态（可选扩展）：**
```bash
curl http://localhost:8000/admin/accounts
```

---

## 🚀 实现优先级

### Phase 1：基础热重载
1. ✅ ConfigLoader（配置加载和验证）
2. ✅ ConfigWatcher（文件监听）
3. ✅ AccountPool.reload（基础重载逻辑）

### Phase 2：状态保留
1. ✅ 保留 Token 和过期时间
2. ✅ 保留冷却状态
3. ✅ Cookie 变化检测

### Phase 3：错误处理
1. ✅ JSON 格式验证
2. ✅ 必填字段验证
3. ✅ 配置回滚机制

### Phase 4：性能优化
1. ✅ 防抖处理
2. ✅ 批量更新
3. ✅ 懒加载 Token

---

## 📚 依赖库

```txt
# requirements.txt 新增
watchdog>=4.0.0  # 文件监听
```

---

**文档版本历史：**
- v1.0 (2025-01-31): 初始版本，完成配置热重载机制设计
