"""
Gemini API Routes - Gemini 原生 API 格式端点

提供与 Gemini API 原生格式兼容的接口。
"""

import logging
import time
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.account_pool import AccountPool
from app.core.gemini_client import GeminiClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1beta", tags=["gemini"])

# 全局账号池
account_pool: Optional[AccountPool] = None


def set_account_pool(pool: AccountPool) -> None:
    """设置全局账号池"""
    global account_pool
    account_pool = pool


# Gemini API 请求/响应模型
class GeminiContent(BaseModel):
    """Gemini 内容部分"""
    text: Optional[str] = Field(None, description="文本内容")
    inline_data: Optional[Dict[str, str]] = Field(None, description="内联数据（图片/视频）")


class GeminiPart(BaseModel):
    """Gemini 消息部分"""
    parts: List[GeminiContent] = Field(..., description="内容部分列表")
    role: Optional[str] = Field("user", description="角色：user/model")


class GeminiGenerationConfig(BaseModel):
    """Gemini 生成配置"""
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0)
    top_k: Optional[int] = Field(None, ge=0)
    max_output_tokens: Optional[int] = Field(None, ge=1)
    stop_sequences: Optional[List[str]] = None


class GeminiGenerateContentRequest(BaseModel):
    """Gemini generateContent 请求"""
    contents: List[GeminiPart] = Field(..., description="对话内容")
    generation_config: Optional[GeminiGenerationConfig] = Field(None, description="生成配置")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "contents": [
                        {
                            "parts": [
                                {"text": "Hello, how are you?"}
                            ],
                            "role": "user"
                        }
                    ]
                }
            ]
        }
    }


class GeminiCandidate(BaseModel):
    """Gemini 响应候选"""
    content: GeminiPart
    finish_reason: str = "STOP"
    index: int = 0
    safety_ratings: List[Dict[str, Any]] = []


class GeminiUsageMetadata(BaseModel):
    """Gemini 使用统计"""
    prompt_token_count: int
    candidates_token_count: int
    total_token_count: int


class GeminiGenerateContentResponse(BaseModel):
    """Gemini generateContent 响应"""
    candidates: List[GeminiCandidate]
    usage_metadata: Optional[GeminiUsageMetadata] = None


@router.post("/models/{model}:generateContent")
async def generate_content(
    model: str,
    request: GeminiGenerateContentRequest
) -> GeminiGenerateContentResponse:
    """
    生成内容（Gemini 原生格式）

    Args:
        model: 模型名称（例如：gemini-2.0-flash）
        request: Gemini 格式的生成请求

    Returns:
        GeminiGenerateContentResponse: Gemini 格式的响应
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
    if not request.contents:
        raise HTTPException(
            status_code=400,
            detail="No content provided"
        )

    # 获取最后一条用户消息
    last_content = request.contents[-1]
    user_message = ""

    for part in last_content.parts:
        if part.text:
            user_message += part.text + " "

    user_message = user_message.strip()

    if not user_message:
        raise HTTPException(
            status_code=400,
            detail="No text content in user message"
        )

    # 发送消息到 Gemini
    try:
        async with GeminiClient(account) as client:
            # 构建请求参数
            kwargs = {}
            if request.generation_config:
                if request.generation_config.temperature is not None:
                    kwargs["temperature"] = request.generation_config.temperature
                if request.generation_config.max_output_tokens is not None:
                    kwargs["max_tokens"] = request.generation_config.max_output_tokens

            # 调用 Gemini API
            result = await client.send_message_with_retry(
                message=user_message,
                **kwargs
            )

            response_text = result.get("response", "")

            # 简单的 token 估算
            prompt_tokens = len(user_message) // 4
            completion_tokens = len(response_text) // 4

            # 构建 Gemini 格式的响应
            return GeminiGenerateContentResponse(
                candidates=[
                    GeminiCandidate(
                        content=GeminiPart(
                            parts=[
                                GeminiContent(text=response_text)
                            ],
                            role="model"
                        ),
                        finish_reason="STOP",
                        index=0,
                        safety_ratings=[]
                    )
                ],
                usage_metadata=GeminiUsageMetadata(
                    prompt_token_count=prompt_tokens,
                    candidates_token_count=completion_tokens,
                    total_token_count=prompt_tokens + completion_tokens
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
async def list_gemini_models():
    """
    列出可用模型（Gemini 格式）

    Returns:
        dict: Gemini 格式的模型列表
    """
    return {
        "models": [
            {
                "name": "models/gemini-2.0-flash",
                "display_name": "Gemini 2.0 Flash",
                "description": "Fast and versatile performance across a diverse variety of tasks",
                "supported_generation_methods": ["generateContent", "countTokens"]
            },
            {
                "name": "models/gemini-1.5-pro",
                "display_name": "Gemini 1.5 Pro",
                "description": "Mid-size multimodal model that supports up to 2 million tokens",
                "supported_generation_methods": ["generateContent", "countTokens"]
            },
            {
                "name": "models/gemini-1.5-flash",
                "display_name": "Gemini 1.5 Flash",
                "description": "Fast and versatile multimodal model for scaling across diverse tasks",
                "supported_generation_methods": ["generateContent", "countTokens"]
            }
        ]
    }
