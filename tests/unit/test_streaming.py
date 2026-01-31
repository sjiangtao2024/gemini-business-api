"""
Unit tests for Streaming Utilities

测试 SSE 流式响应功能。
"""

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from app.utils.streaming import (
    OpenAIStreamFormatter,
    StreamingResponse,
    format_sse_done,
    format_sse_message,
    stream_gemini_response,
)


class TestStreamingResponse:
    """测试 StreamingResponse 类"""

    @pytest.mark.asyncio
    async def test_generate_openai_stream(self):
        """测试生成 OpenAI 流式响应"""
        streaming = StreamingResponse(
            response_text="Hello, World!",
            conversation_id="conv-123",
            model="gemini-2.0-flash"
        )

        chunks = []
        async for chunk in streaming.generate_openai_stream():
            chunks.append(chunk)

        # 验证至少有首个 chunk、内容 chunks 和结束 chunk
        assert len(chunks) >= 3

        # 验证第一个 chunk 包含角色信息
        first_chunk = json.loads(chunks[0].replace("data: ", "").strip())
        assert first_chunk["choices"][0]["delta"]["role"] == "assistant"

        # 验证最后一个 chunk 是 [DONE]
        assert chunks[-1] == "data: [DONE]\n\n"

    @pytest.mark.asyncio
    async def test_stream_contains_model_info(self):
        """测试流式响应包含模型信息"""
        streaming = StreamingResponse(
            response_text="Test",
            conversation_id="conv-123",
            model="test-model"
        )

        chunks = []
        async for chunk in streaming.generate_openai_stream():
            if chunk != "data: [DONE]\n\n":
                data = json.loads(chunk.replace("data: ", "").strip())
                chunks.append(data)

        # 所有 chunk 都应该包含模型信息
        for chunk in chunks:
            assert chunk["model"] == "test-model"
            assert chunk["object"] == "chat.completion.chunk"

    @pytest.mark.asyncio
    async def test_stream_finish_reason(self):
        """测试流式响应的完成原因"""
        streaming = StreamingResponse(
            response_text="Test",
            conversation_id="conv-123"
        )

        chunks = []
        async for chunk in streaming.generate_openai_stream():
            if chunk != "data: [DONE]\n\n":
                data = json.loads(chunk.replace("data: ", "").strip())
                chunks.append(data)

        # 最后一个数据 chunk 应该有 finish_reason
        final_chunk = chunks[-1]
        assert final_chunk["choices"][0]["finish_reason"] == "stop"


class TestOpenAIStreamFormatter:
    """测试 OpenAI 流式格式化器"""

    def test_create_chunk_with_role(self):
        """测试创建包含角色的 chunk"""
        chunk = OpenAIStreamFormatter.create_chunk(
            completion_id="test-id",
            role="assistant",
            model="test-model"
        )

        assert chunk["id"] == "test-id"
        assert chunk["object"] == "chat.completion.chunk"
        assert chunk["model"] == "test-model"
        assert chunk["choices"][0]["delta"]["role"] == "assistant"

    def test_create_chunk_with_content(self):
        """测试创建包含内容的 chunk"""
        chunk = OpenAIStreamFormatter.create_chunk(
            completion_id="test-id",
            content="Hello",
            model="test-model"
        )

        assert chunk["choices"][0]["delta"]["content"] == "Hello"
        assert chunk["choices"][0]["finish_reason"] is None

    def test_create_chunk_with_finish_reason(self):
        """测试创建包含完成原因的 chunk"""
        chunk = OpenAIStreamFormatter.create_chunk(
            completion_id="test-id",
            finish_reason="stop",
            model="test-model"
        )

        assert chunk["choices"][0]["finish_reason"] == "stop"
        assert chunk["choices"][0]["delta"] == {}

    def test_format_chunk(self):
        """测试格式化 chunk 为 SSE 消息"""
        chunk = {"test": "data"}
        formatted = OpenAIStreamFormatter.format_chunk(chunk)

        assert formatted.startswith("data: ")
        assert formatted.endswith("\n\n")
        assert json.loads(formatted.replace("data: ", "").strip()) == chunk


class TestHelperFunctions:
    """测试辅助函数"""

    def test_format_sse_message(self):
        """测试格式化 SSE 消息"""
        data = {"key": "value"}
        message = format_sse_message(data)

        assert message.startswith("data: ")
        assert message.endswith("\n\n")
        assert json.loads(message.replace("data: ", "").strip()) == data

    def test_format_sse_done(self):
        """测试格式化 SSE 完成标记"""
        done = format_sse_done()

        assert done == "data: [DONE]\n\n"


class TestStreamGeminiResponse:
    """测试 stream_gemini_response 函数"""

    @pytest.mark.asyncio
    async def test_stream_gemini_response(self):
        """测试流式响应生成"""
        chunks = []
        async for chunk in stream_gemini_response(
            response_text="Hello!",
            conversation_id="conv-123",
            model="gemini-2.0-flash",
            chunk_size=2
        ):
            chunks.append(chunk)

        # 验证有多个 chunk
        assert len(chunks) >= 3

        # 验证最后一个是 [DONE]
        assert chunks[-1] == "data: [DONE]\n\n"

    @pytest.mark.asyncio
    async def test_stream_chunks_valid_json(self):
        """测试流式 chunk 是否为有效 JSON"""
        async for chunk in stream_gemini_response(
            response_text="Test",
            conversation_id="conv-123"
        ):
            if chunk != "data: [DONE]\n\n":
                # 验证可以解析为 JSON
                data_str = chunk.replace("data: ", "").strip()
                data = json.loads(data_str)
                assert "id" in data
                assert "object" in data
                assert "choices" in data
