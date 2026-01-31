"""
Multimodal Utilities - 多模态内容处理工具

支持图片、视频等多模态内容的处理，包括 URL 和 Base64 格式。
"""

import base64
import logging
import mimetypes
from typing import Dict, Any, List, Optional, Union
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


class MultimodalContent:
    """多模态内容处理类"""

    # 支持的图片 MIME 类型
    SUPPORTED_IMAGE_TYPES = {
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/gif",
        "image/webp",
    }

    # 支持的视频 MIME 类型
    SUPPORTED_VIDEO_TYPES = {
        "video/mp4",
        "video/quicktime",
        "video/x-msvideo",
        "video/mpeg",
    }

    @staticmethod
    def is_url(content: str) -> bool:
        """
        检查内容是否为 URL

        Args:
            content: 内容字符串

        Returns:
            bool: 是否为 URL
        """
        try:
            result = urlparse(content)
            return all([result.scheme, result.netloc])
        except Exception:
            return False

    @staticmethod
    def is_base64(content: str) -> bool:
        """
        检查内容是否为 Base64 编码

        Args:
            content: 内容字符串

        Returns:
            bool: 是否为 Base64
        """
        if content.startswith("data:"):
            # Data URI 格式：data:image/png;base64,xxxxx
            return True

        # 尝试解码验证
        try:
            if len(content) < 100:  # Base64 图片通常很长
                return False
            base64.b64decode(content, validate=True)
            return True
        except Exception:
            return False

    @staticmethod
    async def fetch_image_from_url(url: str) -> Dict[str, Any]:
        """
        从 URL 获取图片

        Args:
            url: 图片 URL

        Returns:
            Dict: 包含 data 和 mime_type 的字典

        Raises:
            ValueError: URL 无效或图片类型不支持
            httpx.HTTPError: HTTP 请求错误
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(url)
                response.raise_for_status()

                # 获取 MIME 类型
                content_type = response.headers.get("content-type", "")
                mime_type = content_type.split(";")[0].strip()

                # 验证图片类型
                if mime_type not in MultimodalContent.SUPPORTED_IMAGE_TYPES:
                    raise ValueError(
                        f"Unsupported image type: {mime_type}. "
                        f"Supported types: {', '.join(MultimodalContent.SUPPORTED_IMAGE_TYPES)}"
                    )

                # 获取图片数据
                image_data = response.content

                logger.debug(f"Fetched image from URL: {url}, size: {len(image_data)} bytes")

                return {
                    "data": image_data,
                    "mime_type": mime_type,
                }

            except httpx.HTTPError as e:
                logger.error(f"Failed to fetch image from URL {url}: {e}")
                raise

    @staticmethod
    def decode_base64_image(base64_str: str) -> Dict[str, Any]:
        """
        解码 Base64 图片

        Args:
            base64_str: Base64 编码的图片字符串

        Returns:
            Dict: 包含 data 和 mime_type 的字典

        Raises:
            ValueError: Base64 解码失败或格式不正确
        """
        try:
            # 处理 Data URI 格式
            if base64_str.startswith("data:"):
                # 格式：data:image/png;base64,xxxxx
                header, encoded = base64_str.split(",", 1)
                mime_type = header.split(":")[1].split(";")[0]
                image_data = base64.b64decode(encoded)
            else:
                # 纯 Base64 字符串，尝试解码
                image_data = base64.b64decode(base64_str)
                # 尝试从数据推断 MIME 类型
                mime_type = MultimodalContent._detect_mime_type(image_data)

            # 验证 MIME 类型
            if mime_type not in MultimodalContent.SUPPORTED_IMAGE_TYPES:
                raise ValueError(
                    f"Unsupported image type: {mime_type}. "
                    f"Supported types: {', '.join(MultimodalContent.SUPPORTED_IMAGE_TYPES)}"
                )

            logger.debug(f"Decoded Base64 image: {mime_type}, size: {len(image_data)} bytes")

            return {
                "data": image_data,
                "mime_type": mime_type,
            }

        except Exception as e:
            logger.error(f"Failed to decode Base64 image: {e}")
            raise ValueError(f"Invalid Base64 image data: {e}")

    @staticmethod
    def _detect_mime_type(data: bytes) -> str:
        """
        从二进制数据检测 MIME 类型

        Args:
            data: 二进制数据

        Returns:
            str: MIME 类型
        """
        # PNG 文件头
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        # JPEG 文件头
        elif data.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        # GIF 文件头
        elif data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
            return "image/gif"
        # WebP 文件头
        elif data[8:12] == b"WEBP":
            return "image/webp"
        else:
            return "application/octet-stream"

    @staticmethod
    def encode_image_to_base64(image_data: bytes, mime_type: str) -> str:
        """
        将图片数据编码为 Base64 Data URI

        Args:
            image_data: 图片二进制数据
            mime_type: MIME 类型

        Returns:
            str: Base64 Data URI
        """
        encoded = base64.b64encode(image_data).decode("utf-8")
        return f"data:{mime_type};base64,{encoded}"


class GeminiMultimodalFormatter:
    """Gemini 多模态内容格式化器"""

    @staticmethod
    def format_text_message(text: str) -> Dict[str, Any]:
        """
        格式化文本消息

        Args:
            text: 文本内容

        Returns:
            Dict: Gemini 格式的文本消息
        """
        return {
            "parts": [
                {
                    "text": text
                }
            ]
        }

    @staticmethod
    def format_image_message(
        text: str,
        image_data: bytes,
        mime_type: str
    ) -> Dict[str, Any]:
        """
        格式化图片消息

        Args:
            text: 文本内容
            image_data: 图片二进制数据
            mime_type: MIME 类型

        Returns:
            Dict: Gemini 格式的图片消息
        """
        # Gemini API 需要 Base64 编码的图片
        image_base64 = base64.b64encode(image_data).decode("utf-8")

        return {
            "parts": [
                {
                    "text": text
                },
                {
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": image_base64
                    }
                }
            ]
        }

    @staticmethod
    def format_video_message(
        text: str,
        video_data: bytes,
        mime_type: str
    ) -> Dict[str, Any]:
        """
        格式化视频消息

        Args:
            text: 文本内容
            video_data: 视频二进制数据
            mime_type: MIME 类型

        Returns:
            Dict: Gemini 格式的视频消息
        """
        # Gemini API 视频格式与图片类似
        video_base64 = base64.b64encode(video_data).decode("utf-8")

        return {
            "parts": [
                {
                    "text": text
                },
                {
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": video_base64
                    }
                }
            ]
        }

    @staticmethod
    async def process_multimodal_content(
        content: Union[str, List[Dict[str, Any]]]
    ) -> Dict[str, Any]:
        """
        处理多模态内容（OpenAI 格式转 Gemini 格式）

        Args:
            content: OpenAI 格式的消息内容

        Returns:
            Dict: Gemini 格式的消息

        Raises:
            ValueError: 内容格式不正确
        """
        # 如果是纯文本
        if isinstance(content, str):
            return GeminiMultimodalFormatter.format_text_message(content)

        # 如果是多模态内容列表
        if isinstance(content, list):
            text_parts = []
            image_parts = []

            for item in content:
                if item.get("type") == "text":
                    text_parts.append(item["text"])
                elif item.get("type") == "image_url":
                    # 处理图片 URL
                    image_url = item["image_url"]["url"]

                    if MultimodalContent.is_url(image_url):
                        # 从 URL 获取图片
                        image_info = await MultimodalContent.fetch_image_from_url(image_url)
                        image_parts.append(image_info)
                    elif MultimodalContent.is_base64(image_url):
                        # 解码 Base64 图片
                        image_info = MultimodalContent.decode_base64_image(image_url)
                        image_parts.append(image_info)
                    else:
                        raise ValueError(f"Invalid image URL format: {image_url}")

            # 构建 Gemini 消息
            if image_parts:
                # 有图片，使用图片消息格式
                text = " ".join(text_parts) if text_parts else ""
                # 目前只支持单张图片，取第一张
                first_image = image_parts[0]
                return GeminiMultimodalFormatter.format_image_message(
                    text=text,
                    image_data=first_image["data"],
                    mime_type=first_image["mime_type"]
                )
            else:
                # 纯文本
                text = " ".join(text_parts)
                return GeminiMultimodalFormatter.format_text_message(text)

        raise ValueError(f"Unsupported content format: {type(content)}")
