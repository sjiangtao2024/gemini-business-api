# Gemini Business API - 架构设计文档

> 版本：v1.0
> 日期：2025-01-31
> 作者：Yukun

## 📋 项目概述

将 Gemini Business 转换为多 API 格式兼容的接口服务，支持 OpenAI、Gemini、Claude 三种 API 格式。

**核心定位：**
- 个人使用（树莓派5部署）
- Docker 单容器部署
- 智能账号池管理
- 轻量级、低资源消耗

---

## 🎯 核心需求

### 1. 多 API 兼容
- **OpenAI 格式**：`/v1/chat/completions`
- **Gemini 格式**：`/v1beta/models/{model}:generateContent`
- **Claude 格式**：`/v1/messages`

### 2. 智能账号池
- 自动轮询选择可用账号
- 故障自动切换（401/403自动换号）
- 冷却管理（401/403/429触发冷却）
- Token 自动刷新（5分钟有效期，本地生成）
- 账号生命周期管理（30天试用期）

### 3. 流式响应
- SSE (Server-Sent Events) 流式输出
- 支持 `stream: true` 参数

### 4. 多模态支持
- 图片/视频输入（Base64 或 URL）
- 原生图片生成（`-image` 后缀模型）
- 视频生成

### 5. 热重载
- 配置文件监听（`config/accounts.json`）
- 无需重启服务

---

## 🏗️ 技术架构

### 技术栈
- **语言**：Python 3.11
- **框架**：FastAPI 0.110+
- **异步**：asyncio + httpx
- **部署**：Docker + docker-compose
- **配置**：JSON（支持热重载）

### 项目结构
```
gemini-business-api/
├── app/
│   ├── main.py              # FastAPI 主程序
│   ├── config.py            # 配置管理（热重载）
│   ├── models/              # Pydantic 数据模型
│   │   ├── openai.py        # OpenAI 格式
│   │   ├── gemini.py        # Gemini 格式
│   │   └── claude.py        # Claude 格式
│   ├── routes/              # API 路由
│   │   ├── openai.py        # /v1/chat/completions
│   │   ├── gemini.py        # /v1beta/models/*
│   │   └── claude.py        # /v1/messages
│   ├── core/
│   │   ├── account_pool.py  # 账号池管理器
│   │   ├── token_manager.py # Token 刷新逻辑
│   │   └── gemini_client.py # Gemini API 客户端
│   └── utils/
│       ├── streaming.py     # SSE 流式处理
│       └── multimodal.py    # 图片/视频处理
├── config/
│   └── accounts.json        # 账号配置（Docker volume）
├── docs/                    # 设计文档
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## 🔐 账号配置设计

### `config/accounts.json` 格式

```json
{
  "accounts": [
    {
      "email": "gemini1@goodcv.fun",
      "team_id": "1d468dcc-11a5-4adc-8b68-8098e227000c",
      "secure_c_ses": "CSE.AXUaAj95JjqSSOJpFb2-Vkb5X79GlWmlrpQx...",
      "host_c_oses": "COS.AfQtEyDX9akUCVLcm_k036VJ8ZvN8qmmMZ2...",
      "csesidx": "206226908",
      "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
      "created_at": "2025-01-31T10:00:00Z",
      "expires_at": "2025-03-02T10:00:00Z"
    }
  ],
  "settings": {
    "account_expiry_days": 30,
    "expiry_warning_days": 3,
    "auto_rotate_enabled": false,
    "min_accounts": 3,
    "cooldown_401_seconds": 7200,
    "cooldown_403_seconds": 7200,
    "cooldown_429_seconds": 14400
  }
}
```

### 配置说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `email` | ✅ | 注册邮箱地址 |
| `team_id` | ✅ | Gemini Business 团队 ID（自动作为 config_id 使用） |
| `secure_c_ses` | ✅ | Cookie: `__Secure-c-SES` |
| `host_c_oses` | ✅ | Cookie: `__Host-c-OSES` |
| `csesidx` | ✅ | Cookie: `csesidx` |
| `user_agent` | ✅ | 浏览器 User-Agent |
| `created_at` | ✅ | 账号创建时间（ISO 8601格式） |
| `expires_at` | ❌ | 账号过期时间（可选，默认created_at+30天） |

### 如何获取配置？

1. 登录 [Gemini Business](https://business.gemini.google/)
2. 打开浏览器开发者工具（F12）
3. **获取 Cookies**：
   - Application → Cookies → `https://business.gemini.google/`
   - 复制 `__Secure-c-SES`、`__Host-c-OSES`、`csesidx`
4. **获取 team_id**：
   - Network → 找到任意请求的 Payload
   - 查找 `configId` 字段（格式：`projects/xxx/locations/global/configs/xxx`）
   - 提取 UUID 部分即为 team_id
5. **获取 User-Agent**：
   - Console 输入 `navigator.userAgent` 回车

---

## 🔄 Token 刷新机制

### 设计策略：本地生成 JWT（被动刷新）

**核心原理：**
1. 用 Cookie 向 Google 请求签名密钥（xsrfToken）
2. 使用 HMAC-SHA256 算法本地生成 JWT
3. 每次使用前检查过期，自动刷新

#### 刷新流程

```python
# 步骤1: 请求签名密钥
GET https://business.gemini.google/auth/getoxsrf?csesidx={csesidx}
Headers: Cookie: __Secure-c-SES={secure_c_ses}

# 步骤2: 服务器返回密钥（不是JWT！）
Response: {
  "xsrfToken": "base64_encoded_key",
  "keyId": "key_identifier"
}

# 步骤3: 本地生成JWT
key_bytes = base64.decode(xsrfToken)
jwt = hmac_sha256(key_bytes, payload)
# payload包含：iss, aud, sub, iat, exp(now+300秒), nbf
```

#### 自动刷新机制

```python
async def get_token():
    async with lock:
        # 检查是否过期（每次使用前）
        if time.time() > self.expires:
            await self._refresh()  # 过期立即刷新
        return self.jwt
```

### Token 生命周期

```
用户请求 → TokenManager.get_token()
   ↓
检查: time.time() > expires?
   ↓ 是（已过期）
请求 getoxsrf 获取密钥
   ↓
本地生成 JWT (有效期5分钟)
   ↓
设置 expires = now + 270秒 (4.5分钟后刷新)
   ↓
返回 JWT → 调用 Gemini API
   ↓
遇到 401? → 立即刷新（兜底）
```

### 关键参数

| 参数 | 值 | 说明 |
|------|-----|------|
| **JWT 有效期** | 300秒（5分钟） | Payload中的exp字段 |
| **实际刷新时间** | 270秒（4.5分钟） | 提前30秒刷新，避免边界情况 |
| **刷新端点** | `/auth/getoxsrf` | Google服务器返回签名密钥 |
| **签名算法** | HMAC-SHA256 | JWT标准签名算法 |
| **并发保护** | asyncio.Lock | 防止同一账号并发刷新 |
| **Cookie 有效期** | 30天 | Gemini Business试用期限制 |
| **401/403 冷却** | 2小时 | 认证错误后账号冷却时间 |
| **429 冷却** | 4小时 | 限流错误后账号冷却时间 |

### 为什么是5分钟？

- ✅ **安全性高**：Token泄露影响窗口极小
- ✅ **自动化透明**：用户完全无感知
- ✅ **无需后台任务**：使用时检查，简单可靠
- ✅ **资源消耗低**：刷新请求极少（每5分钟一次）

---

## 📊 账号池管理策略

### 轮询策略
- **Round-Robin 轮询**：依次使用可用账号
- **状态筛选**：只选择 `active` 且未在冷却期的账号
- **并发安全**：使用计数器 + 锁保证线程安全

### 故障切换
1. **401/403 认证错误**：
   - 标记账号进入冷却期（2小时）
   - 自动切换下一个可用账号
   - 冷却期后自动恢复

2. **429 限流错误**：
   - 标记账号进入冷却期（4小时）
   - 自动切换下一个可用账号
   - 冷却期后自动恢复

3. **其他错误**（网络、超时等）：
   - 重试当前账号（最多3次）
   - 失败后切换下一个账号

### 账号状态

| 状态 | 说明 | 是否可用 |
|------|------|---------|
| `active` | 正常可用 | ✅ |
| `cooldown_401` | 认证错误冷却中 | ❌ |
| `cooldown_429` | 限流冷却中 | ❌ |
| `expired` | 账号过期（30天试用期结束） | ❌ |
| `expiring_soon` | 即将过期（剩余<3天） | ⚠️ |
| `error` | 连续失败多次 | ❌ |

---

## 📆 账号生命周期管理

### 30天试用期机制

Gemini Business 提供30天免费试用，期间可用邮箱验证码登录。

```
Day 0: 注册账号
  ↓
  获取 Cookie（30天有效）
  ↓
Day 1-27: 正常使用
  - Token 每5分钟自动刷新
  - Cookie 持续有效
  ↓
Day 28-29: 过期预警（剩余<3天）
  - 日志警告：⚠️ 账号即将过期
  - 建议：准备新账号
  ↓
Day 30: 试用期结束
  ↓
  Cookie 失效，账号不可用
  ↓
需要注册新账号
```

### 过期检测逻辑

```python
def is_expired(account) -> bool:
    """检查账号是否过期"""
    if account.expires_at:
        # 使用显式过期时间
        return time.time() > account.expires_at

    # 计算账号年龄
    age_seconds = time.time() - account.created_at
    age_days = age_seconds / 86400

    return age_days >= 30  # 30天过期

def should_warn_expiry(account) -> bool:
    """是否应警告即将过期"""
    remaining_days = get_remaining_days(account)
    return 0 < remaining_days < 3  # 剩余<3天
```

### 自动化管理策略

#### 方案1：手动管理（推荐个人使用）
- 日志警告即将过期的账号
- 用户手动注册新账号
- 手动添加到配置文件

#### 方案2：自动轮换（可选）
- 检测到账号<3天过期
- 自动注册新账号（Playwright + 2925邮箱）
- 自动添加到账号池
- 旧账号过期后自动移除

**配置示例：**
```json
{
  "settings": {
    "auto_rotate_enabled": false,  // 是否启用自动轮换
    "min_accounts": 3,              // 最少保持账号数
    "expiry_warning_days": 3        // 提前几天预警
  }
}
```

---

## 🌐 API 兼容层设计

### OpenAI 格式（`/v1/chat/completions`）

**请求示例：**
```json
{
  "model": "gemini-2.5-flash",
  "messages": [
    {"role": "user", "content": "Hello"}
  ],
  "stream": true
}
```

**响应格式：**
```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "gemini-2.5-flash",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "Hello! How can I help you?"
    },
    "finish_reason": "stop"
  }]
}
```

### Gemini 格式（`/v1beta/models/{model}:generateContent`）

**请求示例：**
```json
{
  "contents": [{
    "parts": [{"text": "Hello"}]
  }]
}
```

### Claude 格式（`/v1/messages`）

**请求示例：**
```json
{
  "model": "gemini-2.5-flash",
  "messages": [
    {"role": "user", "content": "Hello"}
  ],
  "max_tokens": 1024
}
```

---

## 🐳 Docker 部署设计

### Dockerfile
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY app/ ./app/

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### docker-compose.yml
```yaml
version: '3.8'

services:
  gemini-api:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./config:/app/config  # 配置文件热重载
    environment:
      - LOG_LEVEL=INFO
    restart: unless-stopped
```

---

## 📝 下一步设计计划

1. ✅ 架构设计（已完成）
2. ✅ Token 刷新机制（已完成）
3. ⏳ **多 API 兼容层详细设计**
   - OpenAI → Gemini 格式转换
   - Gemini → Gemini 直通
   - Claude → Gemini 格式转换
4. ⏳ **流式响应实现**
   - SSE 事件流设计
   - 错误处理
5. ⏳ **多模态处理**
   - 图片/视频输入
   - 图片生成（-image 后缀）
6. ⏳ **配置热重载**
   - 文件监听机制
   - 无中断重载

---

## 🔍 技术决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| 编程语言 | Python 3.11 | 异步生态成熟，FastAPI 性能优秀 |
| Web 框架 | FastAPI | 原生支持异步、SSE、Pydantic 验证 |
| HTTP 客户端 | httpx | 异步支持，API 类似 requests |
| 配置格式 | JSON | 易于手动编辑和复制粘贴 |
| 部署方式 | Docker | 树莓派5兼容，隔离环境 |
| Token 刷新 | 本地生成JWT | 5分钟有效期，使用时检查，安全高效 |
| config_id | 使用 team_id | 避免重复配置，简化使用 |
| 账号管理 | 30天生命周期 | 自动过期检测，支持手动/自动轮换 |

---

**文档版本历史：**
- v1.1 (2025-01-31): 更新Token刷新机制（本地生成JWT），新增30天账号生命周期管理
- v1.0 (2025-01-31): 初始版本，完成架构设计和 Token 刷新机制
