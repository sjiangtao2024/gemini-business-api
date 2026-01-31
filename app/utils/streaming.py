"""
Streaming Utilities - SSE 流式响应工具

实现 Server-Sent Events (SSE) 流式输出，兼容 OpenAI API 格式。
"""

import asyncio
import json
import logging
import time
from typing import AsyncGenerator, Dict, Any, Optional

logger = logging.getLogger(__name__)


class StreamingResponse:
    """SSE 流式响应生成器"""

    def __init__(self, response_text: str, conversation_id: str, model: str = "gemini-2.0-flash"):
        """
        初始化流式响应生成器

        Args:
            response_text: 完整的响应文本
            conversation_id: 会话 ID
            model: 模型名称
        """
        self.response_text = response_text
        self.conversation_id = conversation_id
        self.model = model
        self.chunk_size = 5  # 每次发送的字符数

    async def generate_openai_stream(self) -> AsyncGenerator[str, None]:
        """
        生成 OpenAI 兼容的流式响应

        格式：
        data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1234567890,"model":"...","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}

        Yields:
            str: SSE 格式的数据块
        """
        # 生成唯一的完成 ID
        completion_id = f"chatcmpl-{int(time.time())}-{hash(self.conversation_id) % 10000}"
        created_timestamp = int(time.time())

        # 首个 chunk - 发送角色信息
        first_chunk = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created_timestamp,
            "model": self.model,
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "role": "assistant"
                    },
                    "finish_reason": None
                }
            ]
        }
        yield f"data: {json.dumps(first_chunk, ensure_ascii=False)}\n\n"

        # 按字符分块发送内容
        for i in range(0, len(self.response_text), self.chunk_size):
            chunk_text = self.response_text[i:i + self.chunk_size]

            chunk = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created_timestamp,
                "model": self.model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "content": chunk_text
                        },
                        "finish_reason": None
                    }
                ]
            }

            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

            # 模拟真实的流式输出延迟
            await asyncio.sleep(0.01)

        # 最后一个 chunk - 标记完成
        final_chunk = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created_timestamp,
            "model": self.model,
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop"
                }
            ]
        }
        yield f"data: {json.dumps(final_chunk, ensure_ascii=False)}\n\n"

        # 发送结束标记
        yield "data: [DONE]\n\n"

        logger.debug(f"Streaming completed for conversation {self.conversation_id}")


def format_sse_message(data: Dict[str, Any]) -> str:
    """
    格式化 SSE 消息

    Args:
        data: 要发送的数据字典

    Returns:
        str: SSE 格式的消息
    """
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def format_sse_done() -> str:
    """
    格式化 SSE 完成标记

    Returns:
        str: SSE 完成标记
    """
    return "data: [DONE]\n\n"


async def stream_gemini_response(
    response_text: str,
    conversation_id: str,
    model: str = "gemini-2.0-flash",
    chunk_size: int = 5
) -> AsyncGenerator[str, None]:
    """
    将 Gemini 响应转换为 OpenAI 兼容的流式输出

    Args:
        response_text: Gemini 返回的完整响应文本
        conversation_id: 会话 ID
        model: 模型名称
        chunk_size: 每次发送的字符数

    Yields:
        str: SSE 格式的数据块
    """
    streaming = StreamingResponse(response_text, conversation_id, model)
    async for chunk in streaming.generate_openai_stream():
        yield chunk


class OpenAIStreamFormatter:
    """OpenAI 流式响应格式化器"""

    @staticmethod
    def create_chunk(
        completion_id: str,
        content: Optional[str] = None,
        role: Optional[str] = None,
        finish_reason: Optional[str] = None,
        model: str = "gemini-2.0-flash"
    ) -> Dict[str, Any]:
        """
        创建 OpenAI 格式的 chunk

        Args:
            completion_id: 完成 ID
            content: 内容文本
            role: 角色（assistant/user）
            finish_reason: 完成原因（stop/length/null）
            model: 模型名称

        Returns:
            Dict: OpenAI chunk 格式
        """
        delta = {}
        if role:
            delta["role"] = role
        if content:
            delta["content"] = content

        return {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": delta,
                    "finish_reason": finish_reason
                }
            ]
        }

    @staticmethod
    def format_chunk(chunk: Dict[str, Any]) -> str:
        """
        将 chunk 格式化为 SSE 消息

        Args:
            chunk: OpenAI chunk 数据

        Returns:
            str: SSE 格式的消息
        """
        return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"


class GeminiStreamFormatter:
    """Gemini 流式响应格式化器"""

    @staticmethod
    async def format_stream(
        response_text: str,
        conversation_id: str,
        chunk_size: int = 10
    ) -> AsyncGenerator[str, None]:
        """
        格式化 Gemini 原生流式响应

        Args:
            response_text: 响应文本
            conversation_id: 会话 ID
            chunk_size: 分块大小

        Yields:
            str: Gemini 格式的流式数据
        """
        # Gemini 原生格式流式输出
        for i in range(0, len(response_text), chunk_size):
            chunk_text = response_text[i:i + chunk_size]

            chunk = {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": chunk_text
                                }
                            ],
                            "role": "model"
                        },
                        "finishReason": None,
                        "index": 0
                    }
                ]
            }

            yield json.dumps(chunk, ensure_ascii=False) + "\n"
            await asyncio.sleep(0.01)

        # 最后一个 chunk
        final_chunk = {
            "candidates": [
                {
                    "content": {
                        "parts": [],
                        "role": "model"
                    },
                    "finishReason": "STOP",
                    "index": 0
                }
            ]
        }

        yield json.dumps(final_chunk, ensure_ascii=False) + "\n"
