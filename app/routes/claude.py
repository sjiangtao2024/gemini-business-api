"""
Claude API Routes - Claude API 格式端点

提供与 Claude API 格式兼容的接口。
"""

import logging
import time
from typing import List, Optional, Union

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.account_pool import AccountPool
from app.core.gemini_client import GeminiClient
from app.utils.streaming import stream_gemini_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["claude"])

# 全局账号池
account_pool: Optional[AccountPool] = None


def set_account_pool(pool: AccountPool) -> None:
    """设置全局账号池"""
    global account_pool
    account_pool = pool


# Claude API 请求/响应模型
class ClaudeContentBlock(BaseModel):
    """Claude 内容块"""
    type: str = Field(..., description="内容类型：text/image")
    text: Optional[str] = Field(None, description="文本内容")
    source: Optional[dict] = Field(None, description="图片源")


class ClaudeMessage(BaseModel):
    """Claude 消息"""
    role: str = Field(..., description="角色：user/assistant")
    content: Union[str, List[ClaudeContentBlock]] = Field(..., description="消息内容")


class ClaudeMessagesRequest(BaseModel):
    """Claude Messages API 请求"""
    model: str = Field(default="claude-3-5-sonnet-20241022", description="模型名称")
    messages: List[ClaudeMessage] = Field(..., description="消息列表")
    max_tokens: int = Field(1024, ge=1, le=4096, description="最大 token 数")
    temperature: Optional[float] = Field(None, ge=0.0, le=1.0, description="温度参数")
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0, description="核采样参数")
    stream: bool = Field(default=False, description="是否启用流式输出")
    system: Optional[str] = Field(None, description="系统提示")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "model": "claude-3-5-sonnet-20241022",
                    "messages": [
                        {"role": "user", "content": "Hello, Claude!"}
                    ],
                    "max_tokens": 1024
                }
            ]
        }
    }


class ClaudeContentBlockResponse(BaseModel):
    """Claude 响应内容块"""
    type: str = "text"
    text: str


class ClaudeUsage(BaseModel):
    """Claude Token 使用统计"""
    input_tokens: int
    output_tokens: int


class ClaudeMessagesResponse(BaseModel):
    """Claude Messages API 响应"""
    id: str
    type: str = "message"
    role: str = "assistant"
    content: List[ClaudeContentBlockResponse]
    model: str
    stop_reason: str = "end_turn"
    stop_sequence: Optional[str] = None
    usage: ClaudeUsage


@router.post("/messages")
async def create_message(request: ClaudeMessagesRequest):
    """
    创建消息（Claude API 兼容）

    支持流式和非流式两种模式。

    Args:
        request: Claude 格式的消息请求

    Returns:
        ClaudeMessagesResponse 或 StreamingResponse
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

    # 提取用户消息
    user_message = ""
    for msg in reversed(request.messages):
        if msg.role == "user":
            if isinstance(msg.content, str):
                user_message = msg.content
            else:
                # 提取文本内容
                for block in msg.content:
                    if block.type == "text" and block.text:
                        user_message += block.text + " "
            break

    user_message = user_message.strip()

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
            if request.max_tokens:
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
                # 返回流式响应（Claude SSE 格式）
                # 注意：这里复用 OpenAI 的流式格式，实际应该实现 Claude 的流式格式
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
                    }
                )
            else:
                # 返回非流式响应（Claude 格式）
                message_id = f"msg_{int(time.time())}"

                # 简单的 token 估算
                input_tokens = len(user_message) // 4
                output_tokens = len(response_text) // 4

                return ClaudeMessagesResponse(
                    id=message_id,
                    type="message",
                    role="assistant",
                    content=[
                        ClaudeContentBlockResponse(
                            type="text",
                            text=response_text
                        )
                    ],
                    model=request.model,
                    stop_reason="end_turn",
                    stop_sequence=None,
                    usage=ClaudeUsage(
                        input_tokens=input_tokens,
                        output_tokens=output_tokens
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
                detail=f"API error: {error_message}",
            )
        else:
            logger.error(f"Unexpected error: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Internal server error: {str(e)}",
            )
