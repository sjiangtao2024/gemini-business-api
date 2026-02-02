"""
OpenAI API Routes - OpenAI 兼容的 API 端点

提供与 OpenAI API 完全兼容的接口，支持流式和非流式响应。
"""

import asyncio
import base64
import logging
import time
from typing import List, Optional, Union

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.account_pool import AccountPool
from app.core.gemini_client import GeminiClient
from app.utils.streaming import stream_gemini_response
from app.utils.multimodal import GeminiMultimodalFormatter
from app.utils.image_generation import extract_image_metadata, parse_generated_files

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["openai"])

# 全局账号池（在启动时初始化）
account_pool: Optional[AccountPool] = None


def set_account_pool(pool: AccountPool) -> None:
    """设置全局账号池"""
    global account_pool
    account_pool = pool


# OpenAI 兼容的请求/响应模型
class ImageUrl(BaseModel):
    """图片 URL"""
    url: str = Field(..., description="图片 URL 或 Base64 Data URI")
    detail: Optional[str] = Field("auto", description="图片详细程度：low/high/auto")


class ContentPart(BaseModel):
    """消息内容部分（支持多模态）"""
    type: str = Field(..., description="内容类型：text/image_url")
    text: Optional[str] = Field(None, description="文本内容")
    image_url: Optional[ImageUrl] = Field(None, description="图片 URL")


class Message(BaseModel):
    """聊天消息（支持多模态）"""
    role: str = Field(..., description="角色：system/user/assistant")
    content: Union[str, List[ContentPart]] = Field(..., description="消息内容（文本或多模态）")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "role": "user",
                    "content": "Hello"
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What's in this image?"},
                        {"type": "image_url", "image_url": {"url": "https://example.com/image.jpg"}}
                    ]
                }
            ]
        }
    }


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


class ImageGenerationRequest(BaseModel):
    """OpenAI 图片生成请求"""
    prompt: str = Field(..., description="图像生成提示词")
    model: str = Field(default="gemini-imagen", description="模型名称")
    n: Optional[int] = Field(1, ge=1, le=10, description="生成图片数量")
    size: Optional[str] = Field(None, description="图片尺寸（可选）")
    response_format: Optional[str] = Field(
        None, description="返回格式：b64_json 或 url"
    )
    quality: Optional[str] = Field(None, description="质量：standard/hd（可选）")
    style: Optional[str] = Field(None, description="风格：natural/vivid（可选）")


class ImageData(BaseModel):
    """OpenAI 图片生成响应数据"""
    b64_json: Optional[str] = None
    url: Optional[str] = None
    revised_prompt: Optional[str] = None
    mime_type: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None


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

    # 提取最后一条用户消息（支持多模态）
    user_message_content = None
    for msg in reversed(request.messages):
        if msg.role == "user":
            user_message_content = msg.content
            break

    if not user_message_content:
        raise HTTPException(
            status_code=400,
            detail="No user message found in messages list"
        )

    # 处理多模态内容
    try:
        gemini_message = await GeminiMultimodalFormatter.process_multimodal_content(
            user_message_content
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid multimodal content: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Failed to process multimodal content: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process multimodal content: {str(e)}"
        )

    # 发送消息到 Gemini
    try:
        # 根据 stream 参数使用不同的处理方式
        if request.stream:
            # 流式模式：在生成器内部管理 client 生命周期
            async def stream_openai_format():
                """将 Gemini 流式响应转换为 OpenAI SSE 格式"""
                import time
                import json

                completion_id = f"chatcmpl-{int(time.time())}"
                created_time = int(time.time())

                # 在生成器内部创建 client（确保生命周期正确）
                async with GeminiClient(account) as client:
                    # 首个 chunk（role 信息）
                    first_chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created_time,
                        "model": request.model,
                        "choices": [{
                            "index": 0,
                            "delta": {"role": "assistant"},
                            "finish_reason": None
                        }]
                    }
                    yield f"data: {json.dumps(first_chunk, ensure_ascii=False)}\n\n"

                    # 构建请求参数
                    kwargs = {}
                    if request.temperature is not None:
                        kwargs["temperature"] = request.temperature
                    if request.max_tokens is not None:
                        kwargs["max_tokens"] = request.max_tokens

                    # 流式获取 Gemini 响应
                    text_generator = await client.send_message_with_retry(
                        message=gemini_message,
                        stream=True,
                        **kwargs
                    )

                    # 逐块转换并发送
                    async for text_chunk in text_generator:
                        chunk = {
                            "id": completion_id,
                            "object": "chat.completion.chunk",
                            "created": created_time,
                            "model": request.model,
                            "choices": [{
                                "index": 0,
                                "delta": {"content": text_chunk},
                                "finish_reason": None
                            }]
                        }
                        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

                    # 最后一个 chunk（finish_reason）
                    final_chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created_time,
                        "model": request.model,
                        "choices": [{
                            "index": 0,
                            "delta": {},
                            "finish_reason": "stop"
                        }]
                    }
                    yield f"data: {json.dumps(final_chunk, ensure_ascii=False)}\n\n"
                    yield "data: [DONE]\n\n"

            return StreamingResponse(
                stream_openai_format(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"
                }
            )

        else:
            # 非流式模式：正常使用 async with
            async with GeminiClient(account) as client:
                # 构建请求参数
                kwargs = {}
                if request.temperature is not None:
                    kwargs["temperature"] = request.temperature
                if request.max_tokens is not None:
                    kwargs["max_tokens"] = request.max_tokens

                # 非流式模式：获取完整响应
                result = await client.send_message_with_retry(
                    message=gemini_message,
                    stream=False,
                    **kwargs
                )

                response_text = result.get("response", "")
                conversation_id = result.get("conversation_id", "")

                import time
                completion_id = f"chatcmpl-{int(time.time())}"

                # 简单的 token 估算（实际应该调用 tokenizer）
                prompt_tokens = len(str(user_message_content)) // 4
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
            logger.error(f"Unexpected error: {e}", exc_info=True)  # 添加 exc_info=True
            raise HTTPException(
                status_code=500,
                detail=f"Internal server error: {str(e)}",
            )


@router.post("/images/generations")
async def generate_images(request: ImageGenerationRequest):
    """
    OpenAI 兼容的图片生成接口
    """
    if account_pool is None:
        raise HTTPException(
            status_code=503,
            detail="Service unavailable: Account pool not initialized",
        )

    # 选择账号
    account = await account_pool.get_available_account()

    max_attempts = 3
    retry_delay_seconds = 3

    try:
        async with GeminiClient(account) as client:
            for attempt in range(1, max_attempts + 1):
                result = await client.send_message_with_retry(
                    message=request.prompt,
                    stream=False,
                    model=request.model,
                )

                raw_chunks = result.get("raw_data", [])
                file_ids, session_name = parse_generated_files(raw_chunks)
                if not session_name:
                    session_name = result.get("conversation_id", "")

                if not file_ids or not session_name:
                    logger.warning(
                        "Image generation missing files: files=%s session=%s raw_chunks=%s",
                        len(file_ids),
                        session_name,
                        str(raw_chunks[:2])[:800],
                    )
                    if attempt < max_attempts:
                        logger.warning(
                            "Image generation returned no files (attempt %s/%s), retrying...",
                            attempt,
                            max_attempts,
                        )
                        await asyncio.sleep(retry_delay_seconds)
                        continue
                    raise HTTPException(
                        status_code=502,
                        detail="Image generation returned no files",
                    )

                metadata = await client.list_session_file_metadata(session_name)

                response_format = request.response_format or "b64_json"
                if response_format not in ("b64_json", "url"):
                    raise HTTPException(
                        status_code=400,
                        detail="response_format must be 'b64_json' or 'url'",
                    )

                tasks = []
                for file_info in file_ids[: request.n or 1]:
                    fid = file_info["fileId"]
                    meta = metadata.get(fid, {})
                    mime = meta.get("mimeType", file_info.get("mimeType", "image/png"))
                    correct_session = meta.get("session") or session_name
                    tasks.append((fid, mime, client.download_file(correct_session, fid)))

                results = await asyncio.gather(
                    *[task for _, _, task in tasks],
                    return_exceptions=True,
                )

                data_list = []
                for (fid, mime, _), result_data in zip(tasks, results):
                    if isinstance(result_data, Exception):
                        logger.error("Image download failed: %s (%s)", fid, result_data)
                        continue

                    b64_data = base64.b64encode(result_data).decode("utf-8")
                    metadata = extract_image_metadata(result_data, mime)
                    if response_format == "url":
                        data_list.append({
                            "url": f"data:{mime};base64,{b64_data}",
                            "revised_prompt": request.prompt,
                            **metadata,
                        })
                    else:
                        data_list.append({
                            "b64_json": b64_data,
                            "revised_prompt": request.prompt,
                            **metadata,
                        })

                if data_list:
                    return {
                        "created": int(time.time()),
                        "data": data_list,
                    }

                if attempt < max_attempts:
                    logger.warning(
                        "Image download returned empty results (attempt %s/%s), retrying...",
                        attempt,
                        max_attempts,
                    )
                    await asyncio.sleep(retry_delay_seconds)
                    continue

                raise HTTPException(
                    status_code=502,
                    detail="Image generation returned empty results",
                )

    except Exception as e:
        if hasattr(e, "response"):
            status_code = e.response.status_code
            error_message = str(e)
            account_pool.handle_error(account, status_code, error_message)
            raise HTTPException(
                status_code=status_code,
                detail=f"Gemini API error: {error_message}",
            )

        logger.error("Unexpected error in image generation: %s", e, exc_info=True)
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
                "id": "gemini-auto",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "google",
                "permission": [],
                "root": "gemini-auto",
                "parent": None,
            },
            {
                "id": "gemini-2.5-flash",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "google",
                "permission": [],
                "root": "gemini-2.5-flash",
                "parent": None,
            },
            {
                "id": "gemini-2.5-pro",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "google",
                "permission": [],
                "root": "gemini-2.5-pro",
                "parent": None,
            },
            {
                "id": "gemini-3-flash-preview",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "google",
                "permission": [],
                "root": "gemini-3-flash-preview",
                "parent": None,
            },
            {
                "id": "gemini-3-pro-preview",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "google",
                "permission": [],
                "root": "gemini-3-pro-preview",
                "parent": None,
            },
            {
                "id": "gemini-imagen",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "google",
                "permission": [],
                "root": "gemini-imagen",
                "parent": None,
            },
            {
                "id": "gemini-veo",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "google",
                "permission": [],
                "root": "gemini-veo",
                "parent": None,
            }
        ]
    }
