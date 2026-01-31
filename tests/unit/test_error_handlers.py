"""
Unit tests for Error Handlers

测试全局异常处理和统一错误响应格式。
"""

from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import HTTPException, Request, status
from pydantic import BaseModel, ValidationError

from app.core.error_handlers import (
    ErrorResponse,
    general_exception_handler,
    http_exception_handler,
    httpx_exception_handler,
    validation_exception_handler,
)


class TestErrorResponse:
    """测试 ErrorResponse 类"""

    def test_error_response_basic(self):
        """测试基本错误响应"""
        error = ErrorResponse(
            error_code="TEST_ERROR",
            message="Test error message",
            status_code=400,
        )

        response_dict = error.to_dict()

        assert response_dict["error"]["code"] == "TEST_ERROR"
        assert response_dict["error"]["message"] == "Test error message"
        assert response_dict["error"]["status"] == 400

    def test_error_response_with_details(self):
        """测试带详细信息的错误响应"""
        error = ErrorResponse(
            error_code="TEST_ERROR",
            message="Test error",
            status_code=400,
            details={"field": "email", "reason": "invalid format"},
        )

        response_dict = error.to_dict()

        assert "details" in response_dict["error"]
        assert response_dict["error"]["details"]["field"] == "email"
        assert response_dict["error"]["details"]["reason"] == "invalid format"

    def test_error_response_without_details(self):
        """测试没有详细信息的错误响应"""
        error = ErrorResponse(
            error_code="TEST_ERROR",
            message="Test error",
            status_code=400,
        )

        response_dict = error.to_dict()

        # details 不应该出现在响应中（因为是空的）
        assert "details" not in response_dict["error"]


class TestHttpExceptionHandler:
    """测试 HTTP 异常处理器"""

    @pytest.mark.asyncio
    async def test_handle_400_error(self):
        """测试处理 400 错误"""
        request = MagicMock(spec=Request)
        request.url.path = "/test"
        request.method = "GET"

        exc = HTTPException(status_code=400, detail="Invalid request")

        response = await http_exception_handler(request, exc)

        assert response.status_code == 400
        body = response.body.decode()
        assert "INVALID_REQUEST" in body
        assert "Invalid request" in body

    @pytest.mark.asyncio
    async def test_handle_401_error(self):
        """测试处理 401 错误"""
        request = MagicMock(spec=Request)
        request.url.path = "/api/chat"
        request.method = "POST"

        exc = HTTPException(status_code=401, detail="Unauthorized")

        response = await http_exception_handler(request, exc)

        assert response.status_code == 401
        body = response.body.decode()
        assert "AUTHENTICATION_FAILED" in body

    @pytest.mark.asyncio
    async def test_handle_429_error(self):
        """测试处理 429 速率限制错误"""
        request = MagicMock(spec=Request)
        request.url.path = "/api/chat"
        request.method = "POST"

        exc = HTTPException(status_code=429, detail="Rate limit exceeded")

        response = await http_exception_handler(request, exc)

        assert response.status_code == 429
        body = response.body.decode()
        assert "RATE_LIMIT_EXCEEDED" in body

    @pytest.mark.asyncio
    async def test_handle_500_error(self):
        """测试处理 500 内部错误"""
        request = MagicMock(spec=Request)
        request.url.path = "/api/chat"
        request.method = "POST"

        exc = HTTPException(status_code=500, detail="Internal server error")

        response = await http_exception_handler(request, exc)

        assert response.status_code == 500
        body = response.body.decode()
        assert "INTERNAL_SERVER_ERROR" in body

    @pytest.mark.asyncio
    async def test_handle_503_error(self):
        """测试处理 503 服务不可用错误"""
        request = MagicMock(spec=Request)
        request.url.path = "/api/status"
        request.method = "GET"

        exc = HTTPException(status_code=503, detail="Service unavailable")

        response = await http_exception_handler(request, exc)

        assert response.status_code == 503
        body = response.body.decode()
        assert "SERVICE_UNAVAILABLE" in body


class TestHttpxExceptionHandler:
    """测试 httpx 异常处理器"""

    @pytest.mark.asyncio
    async def test_handle_httpx_status_error_401(self):
        """测试处理 httpx 401 状态错误"""
        request = MagicMock(spec=Request)
        request.url.path = "/api/chat"
        request.method = "POST"

        mock_response = MagicMock()
        mock_response.status_code = 401

        exc = httpx.HTTPStatusError(
            "Unauthorized",
            request=MagicMock(),
            response=mock_response,
        )

        response = await httpx_exception_handler(request, exc)

        assert response.status_code == 502  # Bad Gateway
        body = response.body.decode()
        assert "UPSTREAM_AUTH_FAILED" in body

    @pytest.mark.asyncio
    async def test_handle_httpx_status_error_429(self):
        """测试处理 httpx 429 速率限制错误"""
        request = MagicMock(spec=Request)
        request.url.path = "/api/chat"
        request.method = "POST"

        mock_response = MagicMock()
        mock_response.status_code = 429

        exc = httpx.HTTPStatusError(
            "Rate limit",
            request=MagicMock(),
            response=mock_response,
        )

        response = await httpx_exception_handler(request, exc)

        assert response.status_code == 503  # Service Unavailable
        body = response.body.decode()
        assert "UPSTREAM_RATE_LIMIT" in body

    @pytest.mark.asyncio
    async def test_handle_httpx_request_error(self):
        """测试处理 httpx 网络请求错误"""
        request = MagicMock(spec=Request)
        request.url.path = "/api/chat"
        request.method = "POST"

        exc = httpx.RequestError("Connection failed", request=MagicMock())

        response = await httpx_exception_handler(request, exc)

        assert response.status_code == 503
        body = response.body.decode()
        assert "NETWORK_ERROR" in body

    @pytest.mark.asyncio
    async def test_handle_httpx_status_error_500(self):
        """测试处理 httpx 500 错误"""
        request = MagicMock(spec=Request)
        request.url.path = "/api/chat"
        request.method = "POST"

        mock_response = MagicMock()
        mock_response.status_code = 500

        exc = httpx.HTTPStatusError(
            "Server error",
            request=MagicMock(),
            response=mock_response,
        )

        response = await httpx_exception_handler(request, exc)

        assert response.status_code == 502
        body = response.body.decode()
        assert "UPSTREAM_ERROR" in body


class TestGeneralExceptionHandler:
    """测试一般异常处理器"""

    @pytest.mark.asyncio
    async def test_handle_runtime_error(self):
        """测试处理 RuntimeError"""
        request = MagicMock(spec=Request)
        request.url.path = "/api/chat"
        request.method = "POST"

        exc = RuntimeError("Something went wrong")

        response = await general_exception_handler(request, exc)

        assert response.status_code == 500
        body = response.body.decode()
        assert "INTERNAL_SERVER_ERROR" in body
        assert "RuntimeError" in body

    @pytest.mark.asyncio
    async def test_handle_value_error(self):
        """测试处理 ValueError"""
        request = MagicMock(spec=Request)
        request.url.path = "/api/chat"
        request.method = "POST"

        exc = ValueError("Invalid value")

        response = await general_exception_handler(request, exc)

        assert response.status_code == 500
        body = response.body.decode()
        assert "INTERNAL_SERVER_ERROR" in body
        assert "ValueError" in body

    @pytest.mark.asyncio
    async def test_error_message_does_not_expose_details(self):
        """测试错误消息不暴露内部细节"""
        request = MagicMock(spec=Request)
        request.url.path = "/api/chat"
        request.method = "POST"

        exc = RuntimeError("Internal database connection failed")

        response = await general_exception_handler(request, exc)

        body = response.body.decode()
        # 不应该暴露具体的内部错误信息
        assert "database connection" not in body
        assert "unexpected error occurred" in body.lower()


class TestValidationExceptionHandler:
    """测试 Pydantic 验证异常处理器"""

    @pytest.mark.asyncio
    async def test_handle_validation_error(self):
        """测试处理验证错误"""
        request = MagicMock(spec=Request)
        request.url.path = "/api/chat"
        request.method = "POST"

        # 创建一个简单的 Pydantic 模型来生成验证错误
        class TestModel(BaseModel):
            name: str
            age: int

        try:
            TestModel(name="test", age="invalid")  # age 应该是 int
        except ValidationError as exc:
            response = await validation_exception_handler(request, exc)

            assert response.status_code == 422
            body = response.body.decode()
            assert "VALIDATION_ERROR" in body
            assert "errors" in body
            assert "age" in body

    @pytest.mark.asyncio
    async def test_validation_error_contains_field_info(self):
        """测试验证错误包含字段信息"""
        request = MagicMock(spec=Request)
        request.url.path = "/api/chat"
        request.method = "POST"

        class TestModel(BaseModel):
            email: str
            count: int

        try:
            TestModel(email="", count="not_a_number")
        except ValidationError as exc:
            response = await validation_exception_handler(request, exc)

            body = response.body.decode()
            # 应该包含字段名
            assert "email" in body or "count" in body
