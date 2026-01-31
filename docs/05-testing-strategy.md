# 测试策略文档

> 版本：v1.0
> 日期：2025-01-31

## 📋 概述

本文档定义 Gemini Business API 的完整测试策略，确保系统的可靠性、稳定性和正确性。

**测试目标：**
- ✅ 核心功能正确性（Token 刷新、账号池、API 转换）
- ✅ 多 API 兼容性（OpenAI、Gemini、Claude）
- ✅ 流式响应可靠性
- ✅ 错误处理和容错能力
- ✅ 性能和资源占用

---

## 🎯 测试层级

### 1. 单元测试（Unit Tests）
测试单个函数和类的逻辑正确性。

**覆盖范围：**
- Token Manager（Token 刷新逻辑）
- Account Pool（账号选择、状态管理）
- API Converter（格式转换逻辑）
- MultimodalHandler（图片/视频处理）

**工具：**
- `pytest`（测试框架）
- `pytest-asyncio`（异步测试支持）
- `pytest-mock`（Mock 依赖）

### 2. 集成测试（Integration Tests）
测试多个组件协作的正确性。

**覆盖范围：**
- Token Manager + Gemini API 交互
- Account Pool + Token Manager 集成
- API 路由 + Converter + Gemini Client
- 配置热重载 + Account Pool

### 3. 端到端测试（E2E Tests）
模拟真实用户场景，测试完整流程。

**覆盖范围：**
- OpenAI 接口完整流程（请求 → 转换 → 调用 → 响应）
- 流式响应完整流程
- 多模态请求（图片输入）
- 错误处理流程（401/403/429）

### 4. 性能测试（Performance Tests）
测试系统在负载下的性能表现。

**覆盖范围：**
- 并发请求处理能力
- 内存占用和泄漏检测
- 响应时间分布

---

## 🧪 单元测试设计

### 1. Token Manager 测试

```python
# tests/unit/test_token_manager.py

import pytest
from unittest.mock import AsyncMock, patch
from app.core.token_manager import TokenManager

@pytest.mark.asyncio
async def test_get_token_first_time():
    """测试首次获取 Token"""
    # Arrange
    account_config = {
        "team_id": "test-team-id",
        "secure_c_ses": "test-cookie",
        "csesidx": "12345",
        "user_agent": "test-ua"
    }

    manager = TokenManager(account_config)

    # Mock Gemini API 响应
    with patch('httpx.AsyncClient.get') as mock_get:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"token": "test-jwt-token"}
        mock_get.return_value = mock_response

        # Act
        token = await manager.get_token()

        # Assert
        assert token == "test-jwt-token"
        assert manager.jwt_token == "test-jwt-token"
        assert manager.token_expires_at > 0


@pytest.mark.asyncio
async def test_get_token_reuse_valid():
    """测试复用有效的 Token"""
    # Arrange
    manager = TokenManager({"team_id": "test"})
    manager.jwt_token = "existing-token"
    manager.token_expires_at = time.time() + 3600  # 1小时后过期

    # Act
    token = await manager.get_token()

    # Assert
    assert token == "existing-token"  # 复用，无需刷新


@pytest.mark.asyncio
async def test_get_token_proactive_refresh():
    """测试主动刷新（剩余 < 1小时）"""
    # Arrange
    manager = TokenManager({"team_id": "test"})
    manager.jwt_token = "old-token"
    manager.token_expires_at = time.time() + 1800  # 30分钟后过期

    # Mock 刷新请求
    with patch('httpx.AsyncClient.get') as mock_get:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"token": "new-token"}
        mock_get.return_value = mock_response

        # Act
        token = await manager.get_token()

        # Assert
        assert token == "new-token"  # 已刷新


@pytest.mark.asyncio
async def test_refresh_failure_401():
    """测试 Token 刷新失败（401）"""
    # Arrange
    manager = TokenManager({"team_id": "test"})

    # Mock 401 响应
    with patch('httpx.AsyncClient.get') as mock_get:
        mock_response = AsyncMock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response

        # Act & Assert
        with pytest.raises(Exception, match="Token刷新失败"):
            await manager.get_token()
```

### 2. Account Pool 测试

```python
# tests/unit/test_account_pool.py

import pytest
from app.core.account_pool import AccountPool

@pytest.mark.asyncio
async def test_add_account():
    """测试添加账号"""
    # Arrange
    pool = AccountPool()
    account_data = {
        "team_id": "test-id",
        "secure_c_ses": "test-cookie",
        "csesidx": "12345",
        "user_agent": "test-ua"
    }

    # Act
    await pool.add_account(account_data)

    # Assert
    assert "test-id" in pool.accounts
    assert pool.accounts["test-id"].status == "active"


@pytest.mark.asyncio
async def test_get_available_account_round_robin():
    """测试轮询选择账号"""
    # Arrange
    pool = AccountPool()
    await pool.add_account({"team_id": "acc-1", ...})
    await pool.add_account({"team_id": "acc-2", ...})
    await pool.add_account({"team_id": "acc-3", ...})

    # Act
    acc1 = await pool.get_available_account()
    acc2 = await pool.get_available_account()
    acc3 = await pool.get_available_account()
    acc4 = await pool.get_available_account()

    # Assert
    assert acc1.team_id == "acc-1"
    assert acc2.team_id == "acc-2"
    assert acc3.team_id == "acc-3"
    assert acc4.team_id == "acc-1"  # 循环


@pytest.mark.asyncio
async def test_get_account_skip_cooldown():
    """测试跳过冷却期账号"""
    # Arrange
    pool = AccountPool()
    acc1 = await pool.add_account({"team_id": "acc-1", ...})
    acc2 = await pool.add_account({"team_id": "acc-2", ...})

    # 设置 acc-1 进入冷却期
    acc1.cooldown_until = time.time() + 3600
    acc1.status = "cooldown"

    # Act
    selected = await pool.get_available_account()

    # Assert
    assert selected.team_id == "acc-2"  # 跳过冷却账号


@pytest.mark.asyncio
async def test_no_available_accounts():
    """测试无可用账号"""
    # Arrange
    pool = AccountPool()
    acc = await pool.add_account({"team_id": "acc-1", ...})
    acc.status = "cooldown"
    acc.cooldown_until = time.time() + 3600

    # Act & Assert
    with pytest.raises(HTTPException, match="No available accounts"):
        await pool.get_available_account()
```

### 3. API Converter 测试

```python
# tests/unit/test_openai_converter.py

import pytest
from app.models.openai import OpenAIChatRequest, OpenAIChatMessage
from app.routes.openai import OpenAIConverter

def test_convert_simple_message():
    """测试简单文本消息转换"""
    # Arrange
    request = OpenAIChatRequest(
        model="gemini-2.5-flash",
        messages=[
            OpenAIChatMessage(role="user", content="Hello")
        ]
    )

    converter = OpenAIConverter()

    # Act
    gemini_request = converter.convert_request(request)

    # Assert
    assert "streamConverseRequest" in gemini_request
    assert gemini_request["streamConverseRequest"]["query"]["input"] == "Hello"


def test_convert_multimodal_message():
    """测试多模态消息转换"""
    # Arrange
    request = OpenAIChatRequest(
        model="gemini-2.5-flash",
        messages=[
            OpenAIChatMessage(
                role="user",
                content=[
                    {"type": "text", "text": "Describe this image"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "https://example.com/image.png"}
                    }
                ]
            )
        ]
    )

    converter = OpenAIConverter()

    # Act
    gemini_request = converter.convert_request(request)

    # Assert
    assert gemini_request["query"]["input"] == "Describe this image"
    # 图片上传逻辑单独测试


def test_convert_system_message():
    """测试 System 消息转换"""
    # Arrange
    request = OpenAIChatRequest(
        model="gemini-2.5-flash",
        messages=[
            OpenAIChatMessage(role="system", content="You are a helpful assistant."),
            OpenAIChatMessage(role="user", content="Hello")
        ]
    )

    converter = OpenAIConverter()

    # Act
    gemini_request = converter.convert_request(request)

    # Assert
    # System prompt 应作为首条用户消息
    assert "[System]" in gemini_request["query"]["input"]
```

---

## 🔗 集成测试设计

### 1. Token Manager + Gemini API

```python
# tests/integration/test_token_refresh_integration.py

import pytest
from app.core.token_manager import TokenManager

@pytest.mark.asyncio
@pytest.mark.integration
async def test_real_token_refresh():
    """测试真实的 Token 刷新（需要真实账号）"""
    # 注意：此测试需要配置真实的测试账号
    account_config = {
        "team_id": os.getenv("TEST_TEAM_ID"),
        "secure_c_ses": os.getenv("TEST_SECURE_C_SES"),
        "csesidx": os.getenv("TEST_CSESIDX"),
        "user_agent": os.getenv("TEST_USER_AGENT")
    }

    if not account_config["team_id"]:
        pytest.skip("No test account configured")

    manager = TokenManager(account_config)

    # Act
    token = await manager.get_token()

    # Assert
    assert token is not None
    assert len(token) > 0
    assert manager.token_expires_at > time.time()
```

### 2. Account Pool + Config Reload

```python
# tests/integration/test_config_reload_integration.py

import pytest
from app.core.account_pool import AccountPool
from app.config import ConfigLoader

@pytest.mark.asyncio
@pytest.mark.integration
async def test_config_reload_preserves_state():
    """测试配置重载保留运行时状态"""
    # Arrange
    config_loader = ConfigLoader("tests/fixtures/accounts.json")
    pool = AccountPool(config_loader)

    # 初始加载
    await pool.reload()

    # 获取账号并设置状态
    account = pool.accounts["test-id-1"]
    account.token_manager.jwt_token = "test-token"
    account.token_manager.token_expires_at = time.time() + 3600
    account.request_count = 100

    # Act - 修改配置文件后重载
    # （这里模拟配置文件变化）
    await pool.reload()

    # Assert - 状态应保留
    reloaded_account = pool.accounts["test-id-1"]
    assert reloaded_account.token_manager.jwt_token == "test-token"
    assert reloaded_account.request_count == 100
```

---

## 🌐 端到端测试设计

### 1. OpenAI 接口完整流程

```python
# tests/e2e/test_openai_endpoint.py

import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
@pytest.mark.e2e
async def test_openai_chat_completions_non_stream():
    """测试 OpenAI 接口非流式响应"""
    # Arrange
    async with AsyncClient(base_url="http://localhost:8000") as client:
        payload = {
            "model": "gemini-2.5-flash",
            "messages": [
                {"role": "user", "content": "Say 'Hello'"}
            ],
            "stream": False
        }

        # Act
        response = await client.post("/v1/chat/completions", json=payload)

        # Assert
        assert response.status_code == 200
        data = response.json()

        assert data["object"] == "chat.completion"
        assert data["model"] == "gemini-2.5-flash"
        assert len(data["choices"]) > 0
        assert "content" in data["choices"][0]["message"]


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_openai_chat_completions_stream():
    """测试 OpenAI 接口流式响应"""
    # Arrange
    async with AsyncClient(base_url="http://localhost:8000") as client:
        payload = {
            "model": "gemini-2.5-flash",
            "messages": [
                {"role": "user", "content": "Count to 5"}
            ],
            "stream": True
        }

        # Act
        async with client.stream("POST", "/v1/chat/completions", json=payload) as response:
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/event-stream"

            chunks = []
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    chunks.append(json.loads(data))

        # Assert
        assert len(chunks) > 0
        assert chunks[0]["object"] == "chat.completion.chunk"
        assert "delta" in chunks[0]["choices"][0]


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_openai_with_image():
    """测试 OpenAI 接口图片输入"""
    async with AsyncClient(base_url="http://localhost:8000") as client:
        payload = {
            "model": "gemini-2.5-flash",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What's in this image?"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "https://via.placeholder.com/150"
                            }
                        }
                    ]
                }
            ]
        }

        response = await client.post("/v1/chat/completions", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert "content" in data["choices"][0]["message"]
```

### 2. 错误处理流程

```python
# tests/e2e/test_error_handling.py

@pytest.mark.asyncio
@pytest.mark.e2e
async def test_401_auto_retry():
    """测试 401 错误自动重试"""
    # 需要 Mock Gemini API，模拟 401 后刷新成功
    pass


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_429_cooldown():
    """测试 429 限流触发冷却"""
    # 模拟 429 响应，验证账号进入冷却期
    pass


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_no_available_accounts_503():
    """测试所有账号不可用返回 503"""
    # 确保所有账号都在冷却期，验证返回 503
    pass
```

---

## 📊 性能测试设计

### 1. 并发测试

```python
# tests/performance/test_concurrent_requests.py

import pytest
import asyncio
from httpx import AsyncClient

@pytest.mark.asyncio
@pytest.mark.performance
async def test_concurrent_100_requests():
    """测试 100 并发请求"""
    # Arrange
    async def make_request(client):
        payload = {
            "model": "gemini-2.5-flash",
            "messages": [{"role": "user", "content": "Hello"}]
        }
        return await client.post("/v1/chat/completions", json=payload)

    # Act
    async with AsyncClient(base_url="http://localhost:8000") as client:
        start = time.time()
        tasks = [make_request(client) for _ in range(100)]
        responses = await asyncio.gather(*tasks)
        elapsed = time.time() - start

    # Assert
    success_count = sum(1 for r in responses if r.status_code == 200)

    assert success_count >= 95  # 至少95%成功
    assert elapsed < 30  # 30秒内完成
    print(f"100 requests in {elapsed:.2f}s, {success_count}/100 successful")
```

### 2. 内存泄漏检测

```python
# tests/performance/test_memory_leak.py

import pytest
import psutil
import os

@pytest.mark.asyncio
@pytest.mark.performance
async def test_memory_leak():
    """测试长时间运行的内存泄漏"""
    # Arrange
    process = psutil.Process(os.getpid())
    initial_memory = process.memory_info().rss / 1024 / 1024  # MB

    # Act - 执行 1000 次请求
    async with AsyncClient(base_url="http://localhost:8000") as client:
        for _ in range(1000):
            await client.post("/v1/chat/completions", json={
                "model": "gemini-2.5-flash",
                "messages": [{"role": "user", "content": "Test"}]
            })

    final_memory = process.memory_info().rss / 1024 / 1024  # MB

    # Assert - 内存增长不超过 100MB
    memory_increase = final_memory - initial_memory
    assert memory_increase < 100, f"Memory increased by {memory_increase:.2f} MB"
```

### 3. 响应时间测试

```python
# tests/performance/test_response_time.py

@pytest.mark.asyncio
@pytest.mark.performance
async def test_p95_response_time():
    """测试 P95 响应时间"""
    # Arrange
    times = []

    async with AsyncClient(base_url="http://localhost:8000") as client:
        for _ in range(100):
            start = time.time()
            await client.post("/v1/chat/completions", json={
                "model": "gemini-2.5-flash",
                "messages": [{"role": "user", "content": "Hello"}]
            })
            elapsed = time.time() - start
            times.append(elapsed)

    # Act
    times.sort()
    p50 = times[50]
    p95 = times[95]
    p99 = times[99]

    # Assert
    assert p50 < 2.0, f"P50: {p50:.2f}s"  # 中位数 < 2秒
    assert p95 < 5.0, f"P95: {p95:.2f}s"  # P95 < 5秒

    print(f"Response time - P50: {p50:.2f}s, P95: {p95:.2f}s, P99: {p99:.2f}s")
```

---

## 🛠️ 测试工具和配置

### 1. pytest 配置

```ini
# pytest.ini

[pytest]
minversion = 7.0
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*

# 标记定义
markers =
    unit: 单元测试
    integration: 集成测试
    e2e: 端到端测试
    performance: 性能测试
    slow: 慢速测试

# 异步支持
asyncio_mode = auto

# 日志配置
log_cli = true
log_cli_level = INFO
log_file = tests/pytest.log
log_file_level = DEBUG

# 覆盖率配置
addopts =
    --cov=app
    --cov-report=html
    --cov-report=term-missing
    --maxfail=5
    --tb=short
```

### 2. 测试依赖

```txt
# requirements-test.txt

pytest>=7.4.0
pytest-asyncio>=0.21.0
pytest-cov>=4.1.0
pytest-mock>=3.11.0
httpx>=0.24.0
psutil>=5.9.0
```

### 3. 测试目录结构

```
tests/
├── unit/                  # 单元测试
│   ├── test_token_manager.py
│   ├── test_account_pool.py
│   ├── test_openai_converter.py
│   ├── test_gemini_converter.py
│   └── test_claude_converter.py
├── integration/           # 集成测试
│   ├── test_token_refresh_integration.py
│   ├── test_config_reload_integration.py
│   └── test_multimodal_integration.py
├── e2e/                   # 端到端测试
│   ├── test_openai_endpoint.py
│   ├── test_gemini_endpoint.py
│   ├── test_claude_endpoint.py
│   └── test_error_handling.py
├── performance/           # 性能测试
│   ├── test_concurrent_requests.py
│   ├── test_memory_leak.py
│   └── test_response_time.py
├── fixtures/              # 测试数据
│   ├── accounts.json
│   ├── mock_responses.json
│   └── test_images/
├── conftest.py            # pytest 配置和 fixtures
└── pytest.ini
```

---

## 🔄 CI/CD 集成

### GitHub Actions 配置

```yaml
# .github/workflows/test.yml

name: Tests

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'

    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install -r requirements-test.txt

    - name: Run unit tests
      run: pytest tests/unit -v --cov=app --cov-report=xml

    - name: Run integration tests
      run: pytest tests/integration -v
      env:
        TEST_TEAM_ID: ${{ secrets.TEST_TEAM_ID }}
        TEST_SECURE_C_SES: ${{ secrets.TEST_SECURE_C_SES }}

    - name: Upload coverage
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
        fail_ci_if_error: true
```

---

## 📈 测试覆盖率目标

| 组件 | 目标覆盖率 | 关键路径 |
|------|----------|---------|
| Token Manager | 95%+ | Token 刷新、过期检测 |
| Account Pool | 90%+ | 轮询逻辑、冷却管理 |
| API Converters | 85%+ | 格式转换、错误处理 |
| Multimodal Handler | 80%+ | 图片上传、下载 |
| 整体项目 | 80%+ | - |

---

## 🧹 测试最佳实践

### 1. 测试命名规范

```python
# 好的命名
def test_get_token_when_expired_should_refresh()
def test_account_pool_skips_cooldown_accounts()

# 不好的命名
def test_1()
def test_token()
```

### 2. AAA 模式（Arrange-Act-Assert）

```python
def test_example():
    # Arrange - 准备测试数据
    account = create_test_account()

    # Act - 执行被测试的操作
    result = account.get_status()

    # Assert - 验证结果
    assert result == "active"
```

### 3. 使用 Fixtures

```python
# conftest.py

@pytest.fixture
def test_account():
    """提供测试账号"""
    return {
        "team_id": "test-id",
        "secure_c_ses": "test-cookie",
        "csesidx": "12345",
        "user_agent": "test-ua"
    }


@pytest.fixture
async def account_pool():
    """提供测试账号池"""
    pool = AccountPool()
    await pool.add_account({...})
    yield pool
    # 清理
    await pool.shutdown()
```

### 4. Mock 外部依赖

```python
from unittest.mock import AsyncMock, patch

@patch('httpx.AsyncClient.get')
async def test_with_mock(mock_get):
    mock_get.return_value = AsyncMock(
        status_code=200,
        json=lambda: {"token": "test"}
    )

    # 测试逻辑
```

---

## 🚀 测试执行命令

```bash
# 运行所有测试
pytest

# 运行单元测试
pytest tests/unit -v

# 运行集成测试（需要测试账号）
pytest tests/integration -v

# 运行 E2E 测试（需要服务运行）
pytest tests/e2e -v

# 运行性能测试
pytest tests/performance -v -m performance

# 生成覆盖率报告
pytest --cov=app --cov-report=html
open htmlcov/index.html

# 只运行失败的测试
pytest --lf

# 并行执行（安装 pytest-xdist）
pytest -n auto

# 详细输出
pytest -vv -s
```

---

## 📝 测试清单

### 开发阶段
- [ ] 每个新功能都有对应的单元测试
- [ ] 所有测试都能通过
- [ ] 代码覆盖率 > 80%

### Pull Request 阶段
- [ ] 所有测试通过（CI）
- [ ] 覆盖率不降低
- [ ] 添加新测试覆盖新功能

### 发布前
- [ ] 完整的测试套件通过
- [ ] 性能测试通过
- [ ] 手动 E2E 测试验证

---

**文档版本历史：**
- v1.0 (2025-01-31): 初始版本，完成测试策略设计
