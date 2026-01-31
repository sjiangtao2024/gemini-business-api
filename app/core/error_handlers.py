"""
Error Handlers - 全局异常处理和统一错误响应

提供统一的错误响应格式和全局异常捕获。
"""

import logging
import traceback
from typing import Any, Dict, Optional

from fastapi import Request, status
from fastapi.responses import JSONResponse
import httpx

logger = logging.getLogger(__name__)


class ErrorResponse:
    """统一错误响应格式"""

    def __init__(
        self,
        error_code: str,
        message: str,
        status_code: int,
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        初始化错误响应

        Args:
            error_code: 错误代码（例如：AUTH_FAILED, RATE_LIMIT）
            message: 用户友好的错误消息
            status_code: HTTP 状态码
            details: 可选的详细信息
        """
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        response = {
            "error": {
                "code": self.error_code,
                "message": self.message,
                "status": self.status_code,
            }
        }

        if self.details:
            response["error"]["details"] = self.details

        return response


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    处理 HTTPException 异常

    Args:
        request: FastAPI 请求对象
        exc: 异常实例

    Returns:
        JSONResponse: 统一格式的错误响应
    """
    # 提取状态码和详情
    status_code = getattr(exc, "status_code", status.HTTP_500_INTERNAL_SERVER_ERROR)
    detail = getattr(exc, "detail", str(exc))

    # 根据状态码映射错误代码
    error_code_map = {
        400: "INVALID_REQUEST",
        401: "AUTHENTICATION_FAILED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        429: "RATE_LIMIT_EXCEEDED",
        500: "INTERNAL_SERVER_ERROR",
        503: "SERVICE_UNAVAILABLE",
    }

    error_code = error_code_map.get(status_code, "UNKNOWN_ERROR")

    # 记录错误
    if status_code >= 500:
        logger.error(
            f"HTTP {status_code} error: {detail}",
            extra={
                "path": request.url.path,
                "method": request.method,
                "status_code": status_code,
            },
        )
    else:
        logger.warning(
            f"HTTP {status_code} error: {detail}",
            extra={
                "path": request.url.path,
                "method": request.method,
            },
        )

    # 创建错误响应
    error_response = ErrorResponse(
        error_code=error_code,
        message=detail,
        status_code=status_code,
    )

    return JSONResponse(
        status_code=status_code,
        content=error_response.to_dict(),
    )


async def httpx_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    处理 httpx 相关异常（网络请求失败）

    Args:
        request: FastAPI 请求对象
        exc: httpx 异常实例

    Returns:
        JSONResponse: 统一格式的错误响应
    """
    # 判断异常类型
    if isinstance(exc, httpx.HTTPStatusError):
        # HTTP 状态错误
        status_code = exc.response.status_code
        error_message = f"Upstream API error: {exc}"

        # 根据上游状态码映射
        if status_code in [401, 403]:
            error_code = "UPSTREAM_AUTH_FAILED"
            final_status = status.HTTP_502_BAD_GATEWAY
        elif status_code == 429:
            error_code = "UPSTREAM_RATE_LIMIT"
            final_status = status.HTTP_503_SERVICE_UNAVAILABLE
        else:
            error_code = "UPSTREAM_ERROR"
            final_status = status.HTTP_502_BAD_GATEWAY

    elif isinstance(exc, httpx.RequestError):
        # 网络请求错误
        error_code = "NETWORK_ERROR"
        error_message = f"Network error: {exc}"
        final_status = status.HTTP_503_SERVICE_UNAVAILABLE

    else:
        # 其他 httpx 异常
        error_code = "HTTP_CLIENT_ERROR"
        error_message = f"HTTP client error: {exc}"
        final_status = status.HTTP_500_INTERNAL_SERVER_ERROR

    # 记录错误
    logger.error(
        f"HTTPX error: {error_message}",
        extra={
            "path": request.url.path,
            "method": request.method,
            "exception_type": type(exc).__name__,
        },
    )

    # 创建错误响应
    error_response = ErrorResponse(
        error_code=error_code,
        message=error_message,
        status_code=final_status,
        details={"exception_type": type(exc).__name__},
    )

    return JSONResponse(
        status_code=final_status,
        content=error_response.to_dict(),
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    处理未预期的一般异常

    Args:
        request: FastAPI 请求对象
        exc: 异常实例

    Returns:
        JSONResponse: 统一格式的错误响应
    """
    # 获取异常堆栈
    exc_traceback = "".join(
        traceback.format_exception(type(exc), exc, exc.__traceback__)
    )

    # 记录完整错误信息
    logger.error(
        f"Unhandled exception: {exc}",
        extra={
            "path": request.url.path,
            "method": request.method,
            "exception_type": type(exc).__name__,
            "traceback": exc_traceback,
        },
    )

    # 创建错误响应（不暴露内部错误细节）
    error_response = ErrorResponse(
        error_code="INTERNAL_SERVER_ERROR",
        message="An unexpected error occurred. Please try again later.",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        details={
            "exception_type": type(exc).__name__,
        },
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response.to_dict(),
    )


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    处理 Pydantic 验证异常

    Args:
        request: FastAPI 请求对象
        exc: ValidationError 异常

    Returns:
        JSONResponse: 统一格式的错误响应
    """
    # 提取验证错误详情
    errors = []
    if hasattr(exc, "errors"):
        for error in exc.errors():
            errors.append(
                {
                    "field": ".".join(str(loc) for loc in error["loc"]),
                    "message": error["msg"],
                    "type": error["type"],
                }
            )

    # 记录验证错误
    logger.warning(
        f"Validation error: {errors}",
        extra={
            "path": request.url.path,
            "method": request.method,
        },
    )

    # 创建错误响应
    error_response = ErrorResponse(
        error_code="VALIDATION_ERROR",
        message="Request validation failed",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        details={"errors": errors},
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_response.to_dict(),
    )
