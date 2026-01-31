"""
OpenAI API Routes - OpenAI 兼容的 API 端点

提供与 OpenAI API 完全兼容的接口，支持流式和非流式响应。
"""

import logging
from typing import List, Optional, Union

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.account_pool import AccountPool
from app.core.gemini_client import GeminiClient
from app.utils.streaming import stream_gemini_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["openai"])

# 全局账号池（在启动时初始化）
account_pool: Optional[AccountPool] = None


def set_account_pool(pool: AccountPool) -> None:
    """设置全局账号池"""
    global account_pool
    account_pool = pool


# OpenAI 兼容的请求/响应模型
class Message(BaseModel):
    """聊天消息"""
    role: str = Field(..., description="角色：system/user/assistant")
    content: str = Field(..., description="消息内容")


class ChatCompletionRequest(BaseModel):
    """OpenAI 聊天完成请求"""
    model: str = Field(default="gemini-2.0-flash", description="模型名称")
    messages: List[Message] = Field(..., description="消息列表")
    stream: bool = Field(default=False, description="是否启用流式输出")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="温度参数")
    max_tokens: Optional[int] = Field(None, ge=1, le=8192, description="最大 token 数")
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0, description="核采样参数")
    n: Optional[int] = Field(1, description="生成的响应数量")
    stop: Optional[Union[str, List[str]]] = Field(None, description="停止序列")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "model": "gemini-2.0-flash",
                    "messages": [
                        {"role": "user", "content": "Hello, how are you?"}
                    ],
                    "stream": False,
                    "temperature": 0.7
                }
            ]
        }
    }


class ChatCompletionChoice(BaseModel):
    """聊天完成选项"""
    index: int
    message: Message
    finish_reason: str


class Usage(BaseModel):
    """Token 使用统计"""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    """OpenAI 聊天完成响应"""
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: Usage


@router.post("/chat/completions")
async def create_chat_completion(request: ChatCompletionRequest):
    """
    创建聊天完成（OpenAI 兼容）

    支持流式和非流式两种模式。

    Args:
        request: OpenAI 格式的聊天请求

    Returns:
        StreamingResponse 或 ChatCompletionResponse
    """
    if account_pool is None:
        raise HTTPException(
            status_code=503,
            detail="Service unavailable: Account pool not initialized",
        )

    # 获取可用账号
    try:
        account = await account_pool.get_available_account()
    except Exception as e:
        logger.error(f"Failed to get available account: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"No available accounts: {str(e)}",
        )

    # 提取最后一条用户消息
    user_message = ""
    for msg in reversed(request.messages):
        if msg.role == "user":
            user_message = msg.content
            break

    if not user_message:
        raise HTTPException(
            status_code=400,
            detail="No user message found in messages list"
        )

    # 发送消息到 Gemini
    try:
        async with GeminiClient(account) as client:
            # 构建请求参数
            kwargs = {}
            if request.temperature is not None:
                kwargs["temperature"] = request.temperature
            if request.max_tokens is not None:
                kwargs["max_tokens"] = request.max_tokens

            # 调用 Gemini API
            result = await client.send_message_with_retry(
                message=user_message,
                **kwargs
            )

            response_text = result.get("response", "")
            conversation_id = result.get("conversation_id", "")

            # 根据 stream 参数返回不同格式
            if request.stream:
                # 返回流式响应
                return StreamingResponse(
                    stream_gemini_response(
                        response_text=response_text,
                        conversation_id=conversation_id,
                        model=request.model,
                        chunk_size=5
                    ),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no"
                    }
                )
            else:
                # 返回非流式响应
                import time
                completion_id = f"chatcmpl-{int(time.time())}"

                # 简单的 token 估算（实际应该调用 tokenizer）
                prompt_tokens = len(user_message) // 4
                completion_tokens = len(response_text) // 4
                total_tokens = prompt_tokens + completion_tokens

                return ChatCompletionResponse(
                    id=completion_id,
                    object="chat.completion",
                    created=int(time.time()),
                    model=request.model,
                    choices=[
                        ChatCompletionChoice(
                            index=0,
                            message=Message(
                                role="assistant",
                                content=response_text
                            ),
                            finish_reason="stop"
                        )
                    ],
                    usage=Usage(
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=total_tokens
                    )
                )

    except Exception as e:
        # 处理错误
        if hasattr(e, "response"):
            status_code = e.response.status_code
            error_message = str(e)
            account_pool.handle_error(account, status_code, error_message)

            raise HTTPException(
                status_code=status_code,
                detail=f"Gemini API error: {error_message}",
            )
        else:
            logger.error(f"Unexpected error: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Internal server error: {str(e)}",
            )


@router.get("/models")
async def list_models():
    """
    列出可用模型（OpenAI 兼容）

    Returns:
        dict: 模型列表
    """
    import time

    return {
        "object": "list",
        "data": [
            {
                "id": "gemini-2.0-flash",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "google",
                "permission": [],
                "root": "gemini-2.0-flash",
                "parent": None,
            },
            {
                "id": "gemini-1.5-pro",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "google",
                "permission": [],
                "root": "gemini-1.5-pro",
                "parent": None,
            },
            {
                "id": "gemini-1.5-flash",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "google",
                "permission": [],
                "root": "gemini-1.5-flash",
                "parent": None,
            }
        ]
    }
