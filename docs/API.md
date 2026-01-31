# API 使用指南

## 快速开始

### 1. 配置账号

复制示例配置文件并填写您的 Gemini Business 账号信息：

```bash
cp config/accounts.json.example config/accounts.json
```

编辑 `config/accounts.json`，填写您的账号凭证：

- `email`: 注册邮箱
- `team_id`: Gemini Business 团队 ID
- `secure_c_ses`: Cookie `__Secure-c-SES` 的值
- `host_c_oses`: Cookie `__Host-c-OSES` 的值
- `csesidx`: Cookie `csesidx` 的值
- `user_agent`: 浏览器 User-Agent
- `created_at`: 账号创建时间（ISO 8601 格式）
- `expires_at`: （可选）账号过期时间

### 2. 启动服务

```bash
# 使用 uvicorn 启动
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 或使用 Docker
docker-compose up -d
```

### 3. 访问 API

- API 文档: http://localhost:8000/docs
- 健康检查: http://localhost:8000/api/v1/status/health

---

## API 端点

### 聊天 API

#### 发送消息

**POST** `/api/v1/chat/send`

发送消息到 Gemini Business。

**请求体：**

```json
{
  "message": "Hello, can you help me?",
  "conversation_id": "conv-123",
  "temperature": 0.7,
  "max_tokens": 1000
}
```

**参数说明：**

- `message` (必需): 用户消息内容，1-10000 字符
- `conversation_id` (可选): 会话 ID，用于保持上下文
- `temperature` (可选): 响应随机性，范围 0.0-2.0
- `max_tokens` (可选): 最大响应 token 数，范围 1-8192

**响应示例：**

```json
{
  "response": "Hello! I'd be happy to help you.",
  "conversation_id": "conv-123",
  "account_email": "gemini1@example.com"
}
```

**错误响应：**

```json
{
  "error": {
    "code": "SERVICE_UNAVAILABLE",
    "message": "No available accounts",
    "status": 503
  }
}
```

---

#### 上传文件

**POST** `/api/v1/chat/upload`

上传图片或视频文件到 Gemini Business。

**请求：**

- Content-Type: `multipart/form-data`
- 字段名: `file`

**支持的文件类型：**

- 图片: PNG, JPEG, GIF, WebP
- 视频: MP4, QuickTime (MOV), AVI

**文件大小限制：** 20 MB

**响应示例：**

```json
{
  "file_id": "file-abc123",
  "filename": "image.png",
  "mime_type": "image/png",
  "account_email": "gemini1@example.com"
}
```

**使用 curl 上传：**

```bash
curl -X POST http://localhost:8000/api/v1/chat/upload \
  -F "file=@/path/to/image.png"
```

---

### 状态监控 API

#### 健康检查

**GET** `/api/v1/status/health`

获取服务健康状态。

**响应示例：**

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "accounts_total": 3,
  "accounts_active": 2
}
```

**状态说明：**

- `healthy`: 50%+ 账号可用
- `degraded`: 1-49% 账号可用
- `unhealthy`: 0% 账号可用

---

#### 账号池状态

**GET** `/api/v1/status/pool`

获取账号池详细统计。

**响应示例：**

```json
{
  "total": 3,
  "active": 2,
  "cooldown": 1,
  "expired": 0,
  "expiring_soon": 1,
  "average_age_days": 15.3
}
```

---

#### 所有账号状态

**GET** `/api/v1/status/accounts`

获取所有账号的详细状态。

**响应示例：**

```json
[
  {
    "email": "gemini1@example.com",
    "team_id": "team-1",
    "status": "ACTIVE",
    "is_available": true,
    "is_expired": false,
    "age_days": 10,
    "remaining_days": 20,
    "cooldown_remaining": 0,
    "request_count": 150,
    "error_count": 0,
    "token_status": {
      "valid": true,
      "expires_at": 1706789400
    }
  },
  {
    "email": "gemini2@example.com",
    "team_id": "team-2",
    "status": "COOLDOWN_429",
    "is_available": false,
    "is_expired": false,
    "age_days": 8,
    "remaining_days": 22,
    "cooldown_remaining": 3600,
    "request_count": 200,
    "error_count": 1,
    "token_status": {
      "valid": true,
      "expires_at": 1706789500
    }
  }
]
```

---

## 错误代码

### 客户端错误 (4xx)

| 错误代码 | HTTP 状态 | 说明 |
|---------|----------|------|
| `INVALID_REQUEST` | 400 | 请求参数无效 |
| `AUTHENTICATION_FAILED` | 401 | 认证失败 |
| `FORBIDDEN` | 403 | 无权访问 |
| `NOT_FOUND` | 404 | 资源不存在 |
| `VALIDATION_ERROR` | 422 | 数据验证失败 |
| `RATE_LIMIT_EXCEEDED` | 429 | 请求频率超限 |

### 服务器错误 (5xx)

| 错误代码 | HTTP 状态 | 说明 |
|---------|----------|------|
| `INTERNAL_SERVER_ERROR` | 500 | 内部服务器错误 |
| `UPSTREAM_ERROR` | 502 | 上游 API 错误 |
| `SERVICE_UNAVAILABLE` | 503 | 服务不可用（无可用账号） |
| `UPSTREAM_AUTH_FAILED` | 502 | 上游认证失败 |
| `UPSTREAM_RATE_LIMIT` | 503 | 上游速率限制 |
| `NETWORK_ERROR` | 503 | 网络连接错误 |

---

## 使用示例

### Python 示例

```python
import requests

# 发送消息
response = requests.post(
    "http://localhost:8000/api/v1/chat/send",
    json={
        "message": "What is the capital of France?",
        "temperature": 0.7
    }
)

result = response.json()
print(f"Response: {result['response']}")
print(f"Used account: {result['account_email']}")

# 上传图片
with open("image.png", "rb") as f:
    files = {"file": f}
    response = requests.post(
        "http://localhost:8000/api/v1/chat/upload",
        files=files
    )

result = response.json()
print(f"File ID: {result['file_id']}")
```

### JavaScript 示例

```javascript
// 发送消息
const response = await fetch('http://localhost:8000/api/v1/chat/send', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    message: 'Hello, Gemini!',
    temperature: 0.7
  })
});

const result = await response.json();
console.log('Response:', result.response);

// 上传文件
const formData = new FormData();
formData.append('file', fileInput.files[0]);

const uploadResponse = await fetch('http://localhost:8000/api/v1/chat/upload', {
  method: 'POST',
  body: formData
});

const uploadResult = await uploadResponse.json();
console.log('File ID:', uploadResult.file_id);
```

### curl 示例

```bash
# 发送消息
curl -X POST http://localhost:8000/api/v1/chat/send \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Hello, how are you?",
    "temperature": 0.7
  }'

# 上传文件
curl -X POST http://localhost:8000/api/v1/chat/upload \
  -F "file=@image.png"

# 健康检查
curl http://localhost:8000/api/v1/status/health

# 账号池状态
curl http://localhost:8000/api/v1/status/pool
```

---

## 账号管理

### 账号生命周期

Gemini Business 账号有 **30 天免费试用期**：

- **第 0-27 天**: 正常使用
- **第 28-29 天**: 警告期（剩余 <3 天）
- **第 30 天**: 试用到期，账号不可用
- **第 30 天后**: 必须注册新账号

### 账号状态

| 状态 | 说明 |
|------|------|
| `ACTIVE` | 正常可用 |
| `COOLDOWN_401` | 认证错误冷却（2 小时） |
| `COOLDOWN_403` | 禁止访问冷却（2 小时） |
| `COOLDOWN_429` | 速率限制冷却（4 小时） |
| `ERROR` | 错误状态（多次失败） |
| `EXPIRED` | 已过期（30 天到期） |

### 轮询策略

系统使用 **Round-robin 轮询**策略：

1. 按顺序轮流使用每个账号
2. 自动跳过冷却、错误、过期的账号
3. 并发请求时使用锁保护账号池

### 故障转移

当账号遇到错误时：

- **401/403 错误**: 设置 2 小时冷却，自动切换到下一个账号
- **429 速率限制**: 设置 4 小时冷却，自动切换
- **其他错误**: 增加错误计数，5 次后标记为 ERROR
- **网络错误**: 自动重试（最多 3 次）

---

## 监控和告警

### 日志级别

系统使用标准的 Python logging：

- `INFO`: 正常操作（账号使用、请求成功）
- `WARNING`: 警告信息（账号即将过期、冷却触发）
- `ERROR`: 错误信息（请求失败、账号错误）

### 账号过期警告

系统会自动记录即将过期的账号：

```
⚠️ Account expiring soon: gemini1@example.com (remaining: 2d)
🟠 Account expires TOMORROW: gemini2@example.com
🔴 Account expires TODAY: gemini3@example.com
```

### 推荐监控指标

- 账号池总数 (`/api/v1/status/pool`)
- 活跃账号数
- 冷却账号数
- 即将过期账号数
- 请求成功率
- 平均响应时间

---

## 性能优化

### 并发处理

- 账号池使用 `asyncio.Lock` 保护并发访问
- Token 管理器支持并发刷新
- 所有 I/O 操作使用 async/await

### Token 缓存

- JWT Token 有效期 5 分钟
- 在 270 秒时主动刷新
- 避免频繁请求上游 API

### 连接池

- httpx 异步 HTTP 客户端
- 自动连接复用
- 30 秒请求超时

---

## 故障排除

### 常见问题

**Q: 503 Service Unavailable - No available accounts**

A: 所有账号都在冷却或已过期。检查：
- `GET /api/v1/status/accounts` 查看账号状态
- 等待冷却时间结束
- 添加新账号到配置文件

**Q: 401 Authentication Failed**

A: 账号认证失败。可能原因：
- Cookie 已过期
- team_id 不正确
- 账号已被封禁

**Q: 文件上传失败 - File too large**

A: 文件超过 20MB 限制。压缩文件或分片上传。

**Q: Account expires TODAY**

A: 账号即将过期（30 天试用期结束）。准备新账号：
1. 注册新的 Gemini Business 账号
2. 提取新账号的 Cookie 和 team_id
3. 添加到 `config/accounts.json`

---

## 安全建议

### 配置文件保护

```bash
# 设置只读权限
chmod 600 config/accounts.json

# 不要提交到 Git
echo "config/accounts.json" >> .gitignore
```

### Cookie 安全

- Cookie 包含敏感认证信息，不要分享
- 定期轮换账号
- 使用独立的 Gemini Business 账号，不要使用个人账号

### 网络安全

- 建议部署在内网或使用 VPN
- 不要暴露到公网
- 使用 HTTPS 反向代理（Nginx、Caddy）

---

## 进阶配置

### 环境变量

```bash
# 日志级别
export LOG_LEVEL=DEBUG

# 配置文件路径
export CONFIG_PATH=/custom/path/accounts.json

# 服务端口
export PORT=8080
```

### CORS 配置

编辑 `app/main.py` 中的 CORS 设置：

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourdomain.com"],  # 限制特定域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 自定义冷却时间

编辑 `config/accounts.json` 中的 `settings`：

```json
{
  "settings": {
    "account_expiry_days": 30,
    "expiry_warning_days": 3,
    "cooldown_401_seconds": 7200,
    "cooldown_403_seconds": 7200,
    "cooldown_429_seconds": 14400
  }
}
```

---

## 获取帮助

- GitHub Issues: https://github.com/your-repo/issues
- 文档: README.md
- API 文档: http://localhost:8000/docs
