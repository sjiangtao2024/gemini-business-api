# API 兼容层设计文档

> 版本：v1.0
> 日期：2025-01-31

## 📋 概述

本文档详细设计三种 API 格式的兼容层实现：
- OpenAI API (`/v1/chat/completions`)
- Gemini API (`/v1beta/models/{model}:generateContent`)
- Claude API (`/v1/messages`)

所有格式最终都转换为 Gemini Business API 调用。

---

## 🔄 Gemini Business API 规范

### 核心端点

**基础 URL**：`https://biz-discoveryengine.googleapis.com/v1alpha`

#### 1. 创建 Session
```http
POST /locations/global/widgetCreateSession
Authorization: Bearer {jwt_token}
Content-Type: application/json

{
  "configId": "{team_id}",
  "additionalParams": {"token": "-"},
  "createSessionRequest": {
    "session": {"name": "", "displayName": ""}
  }
}

Response:
{
  "session": {
    "name": "projects/.../locations/global/configs/.../sessions/{session_id}"
  }
}
```

#### 2. 流式对话
```http
POST /locations/global/widgetStreamConverse
Authorization: Bearer {jwt_token}
Content-Type: application/json

{
  "configId": "{team_id}",
  "additionalParams": {"token": "-"},
  "streamConverseRequest": {
    "name": "{session_name}",
    "query": {
      "input": "用户消息",
      "languageCode": "zh-CN"
    }
  }
}

Response: SSE Stream
data: {"message": {"text": "部分响应"}}
data: [DONE]
```

#### 3. 上传文件
```http
POST /locations/global/widgetAddContextFile
Authorization: Bearer {jwt_token}
Content-Type: application/json

{
  "configId": "{team_id}",
  "additionalParams": {"token": "-"},
  "addContextFileRequest": {
    "name": "{session_name}",
    "fileName": "image.png",
    "mimeType": "image/png",
    "fileContents": "{base64_encoded_data}"
  }
}

Response:
{
  "addContextFileResponse": {
    "fileId": "xxx"
  }
}
```

---

## 🎯 OpenAI API 兼容层

### 端点：`POST /v1/chat/completions`

### 请求格式

```json
{
  "model": "gemini-2.5-flash",
  "messages": [
    {
      "role": "system",
      "content": "You are a helpful assistant."
    },
    {
      "role": "user",
      "content": "Hello"
    },
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "Describe this image"},
        {
          "type": "image_url",
          "image_url": {
            "url": "https://example.com/image.png"
          }
        }
      ]
    }
  ],
  "stream": true,
  "temperature": 0.7,
  "max_tokens": 2048,
  "top_p": 0.9
}
```

### 支持的字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `model` | string | ✅ | 模型名称 |
| `messages` | array | ✅ | 对话消息列表 |
| `stream` | boolean | ❌ | 是否流式输出（默认 false） |
| `temperature` | float | ❌ | 温度参数（0-2，默认1） |
| `max_tokens` | integer | ❌ | 最大输出 token 数 |
| `top_p` | float | ❌ | 核采样参数（0-1） |

### 消息格式

#### 文本消息
```json
{
  "role": "user",
  "content": "Hello"
}
```

#### 多模态消息
```json
{
  "role": "user",
  "content": [
    {"type": "text", "text": "Describe this image"},
    {
      "type": "image_url",
      "image_url": {
        "url": "https://example.com/image.png"
      }
    },
    {
      "type": "image_url",
      "image_url": {
        "url": "data:image/png;base64,iVBORw0KGgo..."
      }
    }
  ]
}
```

### 响应格式

#### 非流式响应
```json
{
  "id": "chatcmpl-{uuid}",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "gemini-2.5-flash",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello! How can I help you?"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 20,
    "total_tokens": 30
  }
}
```

#### 流式响应（SSE）
```
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1234567890,"model":"gemini-2.5-flash","choices":[{"index":0,"delta":{"role":"assistant","content":"Hello"},"finish_reason":null}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1234567890,"model":"gemini-2.5-flash","choices":[{"index":0,"delta":{"content":"!"},"finish_reason":null}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1234567890,"model":"gemini-2.5-flash","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

### 转换逻辑：OpenAI → Gemini

```python
async def openai_to_gemini(request: OpenAIChatRequest):
    """
    OpenAI 格式转换为 Gemini Business API 调用
    """
    # 1. 创建 Session
    session_name = await create_session(account)

    # 2. 处理消息历史
    conversation_context = []
    uploaded_files = []

    for msg in request.messages:
        if msg.role == "system":
            # System prompt 作为首条用户消息
            conversation_context.append({
                "role": "user",
                "text": f"[System]: {msg.content}"
            })

        elif msg.role == "user":
            # 处理文本和多模态内容
            if isinstance(msg.content, str):
                conversation_context.append({
                    "role": "user",
                    "text": msg.content
                })
            elif isinstance(msg.content, list):
                # 多模态内容：文本 + 图片
                text_parts = []
                for part in msg.content:
                    if part.type == "text":
                        text_parts.append(part.text)
                    elif part.type == "image_url":
                        # 上传图片到 Session
                        file_id = await upload_image(
                            session_name,
                            part.image_url.url,
                            account
                        )
                        uploaded_files.append(file_id)

                conversation_context.append({
                    "role": "user",
                    "text": " ".join(text_parts)
                })

        elif msg.role == "assistant":
            conversation_context.append({
                "role": "assistant",
                "text": msg.content
            })

    # 3. 提取最新的用户消息
    last_user_msg = conversation_context[-1]["text"]

    # 4. 构建 Gemini 请求
    gemini_request = {
        "configId": account.team_id,
        "additionalParams": {"token": "-"},
        "streamConverseRequest": {
            "name": session_name,
            "query": {
                "input": last_user_msg,
                "languageCode": "zh-CN"
            }
        }
    }

    # 5. 调用 Gemini API（流式或非流式）
    if request.stream:
        return stream_gemini_to_openai(gemini_request, request.model)
    else:
        return await call_gemini_non_stream(gemini_request, request.model)
```

### 图片处理逻辑

```python
async def upload_image(session_name: str, image_url: str, account):
    """
    上传图片到 Gemini Session

    支持：
    - HTTP/HTTPS URL
    - Data URL (base64)
    """
    if image_url.startswith("data:"):
        # Data URL: data:image/png;base64,iVBORw0KGgo...
        mime_type, base64_data = parse_data_url(image_url)
    else:
        # HTTP URL: 下载图片
        async with httpx.AsyncClient() as client:
            resp = await client.get(image_url)
            resp.raise_for_status()
            mime_type = resp.headers.get("content-type", "image/png")
            base64_data = base64.b64encode(resp.content).decode()

    # 调用 Gemini Upload API
    response = await call_gemini_upload(
        session_name=session_name,
        mime_type=mime_type,
        base64_content=base64_data,
        account=account
    )

    return response["addContextFileResponse"]["fileId"]
```

### 流式响应转换

```python
async def stream_gemini_to_openai(gemini_request, model: str):
    """
    Gemini SSE 流转换为 OpenAI SSE 流
    """
    request_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())

    async def event_generator():
        async for line in call_gemini_stream(gemini_request):
            if line.startswith("data: "):
                data = json.loads(line[6:])

                # Gemini 格式：{"message": {"text": "..."}}
                if "message" in data and "text" in data["message"]:
                    chunk_text = data["message"]["text"]

                    # 转换为 OpenAI 格式
                    openai_chunk = {
                        "id": request_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model,
                        "choices": [{
                            "index": 0,
                            "delta": {"content": chunk_text},
                            "finish_reason": None
                        }]
                    }

                    yield f"data: {json.dumps(openai_chunk)}\n\n"

        # 发送结束标记
        final_chunk = {
            "id": request_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {},
                "finish_reason": "stop"
            }]
        }
        yield f"data: {json.dumps(final_chunk)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )
```

---

## 🧬 Gemini API 兼容层

### 端点：`POST /v1beta/models/{model}:generateContent`

### 请求格式

```json
{
  "contents": [
    {
      "role": "user",
      "parts": [
        {"text": "Hello"}
      ]
    }
  ],
  "generationConfig": {
    "temperature": 0.7,
    "maxOutputTokens": 2048,
    "topP": 0.9
  }
}
```

### 多模态请求

```json
{
  "contents": [
    {
      "role": "user",
      "parts": [
        {"text": "Describe this image"},
        {
          "inline_data": {
            "mime_type": "image/png",
            "data": "iVBORw0KGgo..."
          }
        }
      ]
    }
  ]
}
```

### 响应格式

#### 非流式响应
```json
{
  "candidates": [
    {
      "content": {
        "parts": [
          {"text": "Hello! How can I help you?"}
        ],
        "role": "model"
      },
      "finishReason": "STOP",
      "index": 0
    }
  ],
  "usageMetadata": {
    "promptTokenCount": 10,
    "candidatesTokenCount": 20,
    "totalTokenCount": 30
  }
}
```

#### 流式响应
```json
data: {"candidates":[{"content":{"parts":[{"text":"Hello"}],"role":"model"},"finishReason":"NONE","index":0}]}

data: {"candidates":[{"content":{"parts":[{"text":"!"}],"role":"model"},"finishReason":"NONE","index":0}]}

data: {"candidates":[{"content":{"parts":[{"text":""}],"role":"model"},"finishReason":"STOP","index":0}]}
```

### 转换逻辑：Gemini → Gemini Business

```python
async def gemini_to_gemini_business(request: GeminiGenerateRequest):
    """
    Gemini API 格式转换为 Gemini Business API

    注意：Gemini API 和 Gemini Business API 是不同的端点
    """
    # 1. 创建 Session
    session_name = await create_session(account)

    # 2. 处理 contents
    last_user_message = None
    uploaded_files = []

    for content in request.contents:
        if content.role == "user":
            for part in content.parts:
                if "text" in part:
                    last_user_message = part.text
                elif "inline_data" in part:
                    # 上传 base64 图片
                    file_id = await upload_image_base64(
                        session_name,
                        part.inline_data.mime_type,
                        part.inline_data.data,
                        account
                    )
                    uploaded_files.append(file_id)

    # 3. 构建 Gemini Business 请求
    gemini_business_request = {
        "configId": account.team_id,
        "additionalParams": {"token": "-"},
        "streamConverseRequest": {
            "name": session_name,
            "query": {
                "input": last_user_message,
                "languageCode": "zh-CN"
            }
        }
    }

    # 4. 调用并转换响应
    if request.stream:
        return stream_gemini_business_to_gemini(gemini_business_request)
    else:
        return await call_gemini_business_to_gemini(gemini_business_request)
```

---

## 🤖 Claude API 兼容层

### 端点：`POST /v1/messages`

### 请求格式

```json
{
  "model": "gemini-2.5-flash",
  "messages": [
    {
      "role": "user",
      "content": "Hello"
    },
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "Describe this image"},
        {
          "type": "image",
          "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": "iVBORw0KGgo..."
          }
        }
      ]
    }
  ],
  "max_tokens": 1024,
  "temperature": 0.7,
  "stream": false
}
```

### 支持的字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `model` | string | ✅ | 模型名称 |
| `messages` | array | ✅ | 对话消息列表 |
| `max_tokens` | integer | ✅ | 最大输出 token 数 |
| `stream` | boolean | ❌ | 是否流式输出（默认 false） |
| `temperature` | float | ❌ | 温度参数（0-1） |

### 响应格式

#### 非流式响应
```json
{
  "id": "msg_{uuid}",
  "type": "message",
  "role": "assistant",
  "content": [
    {
      "type": "text",
      "text": "Hello! How can I help you?"
    }
  ],
  "model": "gemini-2.5-flash",
  "stop_reason": "end_turn",
  "usage": {
    "input_tokens": 10,
    "output_tokens": 20
  }
}
```

#### 流式响应
```
event: message_start
data: {"type":"message_start","message":{"id":"msg_xxx","type":"message","role":"assistant","content":[],"model":"gemini-2.5-flash"}}

event: content_block_start
data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"!"}}

event: content_block_stop
data: {"type":"content_block_stop","index":0}

event: message_delta
data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":20}}

event: message_stop
data: {"type":"message_stop"}
```

### 转换逻辑：Claude → Gemini

```python
async def claude_to_gemini(request: ClaudeMessagesRequest):
    """
    Claude API 格式转换为 Gemini Business API
    """
    # 转换逻辑与 OpenAI 类似，主要差异：
    # 1. Claude 图片格式不同：source.type = "base64"
    # 2. Claude 响应格式不同：content 数组包含 text 对象
    # 3. Claude 流式事件类型不同

    # 处理消息
    for msg in request.messages:
        if isinstance(msg.content, list):
            for part in msg.content:
                if part.type == "image":
                    # Claude 图片格式
                    file_id = await upload_image_base64(
                        session_name,
                        part.source.media_type,
                        part.source.data,
                        account
                    )
```

---

## 🎨 图片生成（-image 后缀模型）

### 触发条件
用户请求的模型名称包含 `-image` 后缀（如 `gemini-2.5-flash-image`）

### 处理逻辑

```python
async def handle_image_generation(request, model: str):
    """
    处理图片生成请求

    1. 检查模型名称是否包含 -image
    2. 在用户消息后追加图片生成提示
    3. 解析响应中的图片文件
    4. 返回图片 URL 或 Base64
    """
    # 1. 修改用户消息
    user_prompt = extract_last_user_message(request.messages)
    enhanced_prompt = f"{user_prompt}\n\n请生成一张图片。"

    # 2. 调用 Gemini API
    response = await call_gemini_with_prompt(enhanced_prompt, account)

    # 3. 获取生成的图片文件
    file_metadata = await get_session_file_metadata(
        account,
        session_name,
        filter="file_origin_type = AI_GENERATED"
    )

    # 4. 下载图片
    for file_id, metadata in file_metadata.items():
        image_data = await download_image(
            account,
            session_name,
            file_id
        )

        # 5. 转换为 Base64 或 URL
        if output_format == "base64":
            image_base64 = base64.b64encode(image_data).decode()
            return format_image_response(
                model=model,
                content=f"data:image/png;base64,{image_base64}"
            )
        else:
            # 保存到本地/对象存储，返回 URL
            image_url = await save_image(image_data, file_id)
            return format_image_response(
                model=model,
                content=image_url
            )
```

### OpenAI 格式图片响应

```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "gemini-2.5-flash-image",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "data:image/png;base64,iVBORw0KGgo..."
      },
      "finish_reason": "stop"
    }
  ]
}
```

---

## 🎬 视频生成

### 触发条件
使用专用视频生成模型（如 `gemini-veo`）

### 处理逻辑

```python
async def handle_video_generation(request, model: str):
    """
    处理视频生成请求

    返回格式：HTML embed / URL / Markdown
    """
    # 1. 调用 Gemini API 生成视频
    response = await call_gemini_with_prompt(user_prompt, account)

    # 2. 获取视频文件
    video_metadata = await get_session_file_metadata(
        account,
        session_name,
        filter="file_origin_type = AI_GENERATED AND mime_type LIKE 'video/%'"
    )

    # 3. 下载视频
    video_data = await download_video(account, session_name, video_file_id)

    # 4. 保存并返回 URL
    video_url = await save_video(video_data, video_file_id)

    # 5. 根据配置格式返回
    if output_format == "html":
        content = f'<video src="{video_url}" controls></video>'
    elif output_format == "markdown":
        content = f"![Generated Video]({video_url})"
    else:
        content = video_url

    return format_video_response(model=model, content=content)
```

---

## 🛡️ 错误处理

### 错误码映射

| Gemini Business 错误 | HTTP 状态码 | 说明 | 处理策略 |
|---------------------|-----------|------|---------|
| 401 Unauthorized | 401 | Token 过期 | 刷新 Token 后重试 |
| 403 Forbidden | 403 | 权限不足 | 标记账号冷却（2小时） |
| 429 Too Many Requests | 429 | 限流 | 标记账号冷却（4小时） |
| 400 Bad Request | 400 | 参数错误 | 直接返回给客户端 |
| 500 Internal Error | 500 | 服务器错误 | 重试（最多3次） |

### 错误响应格式

#### OpenAI 格式
```json
{
  "error": {
    "message": "Token expired, please retry",
    "type": "invalid_request_error",
    "code": "token_expired"
  }
}
```

#### Gemini 格式
```json
{
  "error": {
    "code": 401,
    "message": "Token expired",
    "status": "UNAUTHENTICATED"
  }
}
```

#### Claude 格式
```json
{
  "type": "error",
  "error": {
    "type": "authentication_error",
    "message": "Token expired"
  }
}
```

---

## 📊 请求流程图

```
客户端请求 → 路由分发 → 格式验证
    ↓
识别 API 格式 (OpenAI/Gemini/Claude)
    ↓
提取消息和多模态内容
    ↓
从账号池获取可用账号 → Token Manager 获取 JWT
    ↓
创建 Gemini Session
    ↓
上传图片/视频（如有）
    ↓
调用 Gemini Business API
    ↓
流式/非流式响应转换
    ↓
返回对应格式的响应给客户端
```

---

## 🔧 核心组件接口设计

### 1. 格式转换器接口

```python
class APIConverter(ABC):
    """API 格式转换器基类"""

    @abstractmethod
    async def convert_request(self, request) -> GeminiBusinessRequest:
        """将特定格式请求转换为 Gemini Business 请求"""
        pass

    @abstractmethod
    async def convert_response(self, gemini_response) -> dict:
        """将 Gemini Business 响应转换为特定格式"""
        pass

    @abstractmethod
    async def stream_response(self, gemini_stream) -> AsyncGenerator:
        """将 Gemini Business 流式响应转换为特定格式"""
        pass
```

### 2. 多模态处理器

```python
class MultimodalHandler:
    """多模态内容处理器"""

    async def process_images(
        self,
        session_name: str,
        images: List[ImageInput],
        account: Account
    ) -> List[str]:
        """处理图片列表，返回 file_id 列表"""
        pass

    async def download_generated_images(
        self,
        session_name: str,
        account: Account
    ) -> List[bytes]:
        """下载 AI 生成的图片"""
        pass

    async def download_generated_videos(
        self,
        session_name: str,
        account: Account
    ) -> List[bytes]:
        """下载 AI 生成的视频"""
        pass
```

### 3. 响应流转换器

```python
class StreamConverter:
    """流式响应转换器"""

    @staticmethod
    async def gemini_to_openai_stream(
        gemini_stream: AsyncGenerator,
        model: str
    ) -> AsyncGenerator:
        """Gemini SSE → OpenAI SSE"""
        pass

    @staticmethod
    async def gemini_to_claude_stream(
        gemini_stream: AsyncGenerator,
        model: str
    ) -> AsyncGenerator:
        """Gemini SSE → Claude SSE"""
        pass
```

---

## ✅ 实现优先级

### Phase 1：基础功能
1. ✅ OpenAI `/v1/chat/completions` 文本对话（非流式）
2. ✅ Token 刷新和账号池管理
3. ✅ 错误处理和重试机制

### Phase 2：流式响应
1. ✅ OpenAI 流式响应
2. ✅ Gemini 流式响应
3. ✅ Claude 流式响应

### Phase 3：多模态
1. ✅ 图片输入（URL 和 Base64）
2. ✅ 图片生成（-image 模型）
3. ✅ 视频生成

### Phase 4：完整 API 支持
1. ✅ Gemini API 完整支持
2. ✅ Claude API 完整支持
3. ✅ 配置热重载

---

**文档版本历史：**
- v1.0 (2025-01-31): 初始版本，完成三种 API 格式的详细设计
