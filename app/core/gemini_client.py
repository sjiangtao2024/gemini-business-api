"""
Gemini Client - HTTP client for Gemini Business API

Handles HTTP requests to Gemini Business API with:
- Session management with account credentials
- Automatic token refresh integration
- Request/response handling
- Error detection and propagation
"""

import logging
import time
from typing import Any, Dict, Optional

import httpx

from app.models.account import Account

logger = logging.getLogger(__name__)


class GeminiClient:
    """
    HTTP Client for Gemini Business API

    Manages HTTP sessions with account credentials and token management
    """

    # Gemini Business API endpoints
    BASE_URL = "https://biz-discoveryengine.googleapis.com"
    CREATE_SESSION_API = "/v1alpha/locations/global/widgetCreateSession"
    CHAT_API = "/v1alpha/locations/global/widgetStreamAssist"
    UPLOAD_API = "/v1alpha/locations/global/widgetAddContextFile"
    LIST_SESSION_FILES_API = "/v1alpha/locations/global/widgetListSessionFileMetadata"

    # Request configuration
    TIMEOUT = 120.0  # 120 seconds (image generation can be slow)
    MAX_RETRIES = 3
    VIRTUAL_MODELS = {
        "gemini-imagen": {"imageGenerationSpec": {}},
        "gemini-veo": {"videoGenerationSpec": {}},
    }

    def __init__(self, account: Account):
        """
        Initialize Gemini Client

        Args:
            account: Account instance with credentials
        """
        self.account = account
        self._client: Optional[httpx.AsyncClient] = None
        self._session_name: Optional[str] = None  # 缓存的 session name

    async def __aenter__(self):
        """Async context manager entry"""
        await self._ensure_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()

    async def _ensure_client(self) -> None:
        """Ensure HTTP client is initialized"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.TIMEOUT, connect=30.0),
                follow_redirects=True,
            )

    async def close(self) -> None:
        """Close HTTP client"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _get_headers(self, token: str) -> Dict[str, str]:
        """
        Build request headers with account credentials

        Args:
            token: JWT token from TokenManager

        Returns:
            dict: Request headers
        """
        return {
            "accept": "*/*",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "authorization": f"Bearer {token}",
            "content-type": "application/json",
            "origin": "https://business.gemini.google",
            "referer": "https://business.gemini.google/",
            "user-agent": self.account.user_agent,
            "x-server-timeout": "1800",
            "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "cross-site",
        }

    async def _create_session(self) -> str:
        """
        Create a new Google session

        Returns:
            str: Session name (e.g., "projects/xxx/sessions/xxx")

        Raises:
            httpx.HTTPStatusError: On HTTP errors
        """
        await self._ensure_client()

        # Get fresh token
        token = await self.account.token_manager.get_token()

        # Build request
        url = f"{self.BASE_URL}{self.CREATE_SESSION_API}"
        headers = self._get_headers(token)
        payload = {
            "configId": self.account.team_id,
            "additionalParams": {"token": "-"},
            "createSessionRequest": {
                "session": {"name": "", "displayName": ""}
            }
        }

        logger.debug(f"[SESSION] Creating session for account: {self.account.email}")

        response = await self._client.post(
            url,
            headers=headers,
            json=payload,
        )

        # Check for errors and log details
        if response.status_code != 200:
            error_detail = response.text
            logger.error(
                f"[SESSION] Failed to create session: HTTP {response.status_code}\n"
                f"Response: {error_detail[:500]}"
            )
            response.raise_for_status()

        # Parse response
        data = response.json()
        session_name = data.get("session", {}).get("name", "")

        if not session_name:
            raise Exception("Session name not found in response")

        logger.info(f"[SESSION] Created session: {session_name[-12:]}")
        return session_name

    async def send_message(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        stream: bool = False,
        **kwargs
    ):
        """
        Send message to Gemini Business API (支持流式和非流式)

        Args:
            message: User message to send (can be string or dict for multimodal)
            conversation_id: Optional conversation ID for context (not used, for compatibility)
            stream: If True, return async generator; if False, return complete response
            **kwargs: Additional request parameters (model, temperature, etc.)

        Returns:
            AsyncIterator[str] (if stream=True) or dict (if stream=False)

        Raises:
            httpx.HTTPStatusError: On HTTP errors
            httpx.RequestError: On network errors
        """
        await self._ensure_client()

        # Get fresh token from account's token manager
        token = await self.account.token_manager.get_token()

        # Create new session (or reuse cached one)
        if not self._session_name:
            self._session_name = await self._create_session()

        # 处理 message：可能是字符串或字典（多模态）
        if isinstance(message, str):
            query_parts = [{"text": message}]
        elif isinstance(message, dict):
            # 如果是字典，假设已经是正确的格式
            query_parts = message.get("parts", [{"text": str(message)}])
        else:
            query_parts = [{"text": str(message)}]

        # Build request payload
        model_name = kwargs.get("model", "gemini-2.5-flash")

        # 工具配置
        if model_name in self.VIRTUAL_MODELS:
            tools_spec = self.VIRTUAL_MODELS[model_name]
            # Match web behavior: image generation uses toolsSpec + a base model.
            model_id_for_config = "gemini-2.5-flash" if model_name == "gemini-imagen" else None
        else:
            tools_spec = {
                "webGroundingSpec": {},
                "toolRegistry": "default_tool_registry",
                "imageGenerationSpec": {},
                "videoGenerationSpec": {}
            }
            model_id_for_config = model_name

        payload = {
            "configId": self.account.team_id,
            "additionalParams": {"token": "-"},
            "streamAssistRequest": {
                "session": self._session_name,
                "query": {"parts": query_parts},
                "filter": "",
                "fileIds": [],
                "answerGenerationMode": "NORMAL",
                "toolsSpec": tools_spec,
                "languageCode": "zh-CN",
                "userMetadata": {"timeZone": "Asia/Shanghai"},
                "assistSkippingMode": "REQUEST_ASSIST"
            }
        }

        # 添加模型配置
        if model_id_for_config:
            payload["streamAssistRequest"]["assistGenerationConfig"] = {
                "modelId": model_id_for_config
            }

        # Send request
        url = f"{self.BASE_URL}{self.CHAT_API}"
        headers = self._get_headers(token)

        # 智能处理 message 日志（支持字符串和字典类型）
        if isinstance(message, str):
            message_preview = message[:50] if len(message) > 50 else message
        else:
            message_preview = str(message)[:50]

        logger.debug(
            f"Sending message to Gemini API: {message_preview}... "
            f"(stream={stream}, account: {self.account.email})"
        )

        # 流式模式：返回异步生成器
        if stream:
            return self._stream_response(url, headers, payload)

        # 非流式模式：收集完整响应
        else:
            return await self._get_complete_response(url, headers, payload)

    async def _stream_response(self, url: str, headers: Dict[str, str], payload: Dict[str, Any]):
        """
        流式处理响应（使用 httpx.stream）

        Yields:
            str: 流式文本块
        """
        from app.utils.streaming_parser import parse_json_array_stream_async

        async with self._client.stream("POST", url, json=payload, headers=headers) as response:
            # Check for errors
            if response.status_code != 200:
                error_text = await response.aread()
                logger.error(
                    f"Gemini API error: HTTP {response.status_code}\n"
                    f"Response: {error_text.decode()[:500]}"
                )
                response.raise_for_status()

            # 逐块解析 JSON 数组流
            async for chunk in parse_json_array_stream_async(response.aiter_lines()):
                # 提取文本内容
                stream_assist = chunk.get("streamAssistResponse", {})
                answer = stream_assist.get("answer", {})
                replies = answer.get("replies", [])

                for reply in replies:
                    grounded_content = reply.get("groundedContent", {})
                    content = grounded_content.get("content", {})
                    text = content.get("text", "")
                    is_thought = content.get("thought", False)

                    # 跳过思考过程（thought: true），只返回实际答案
                    if text and not is_thought:
                        yield text

    async def _get_complete_response(self, url: str, headers: Dict[str, str], payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        非流式处理：收集完整响应

        Returns:
            dict: 完整响应数据
        """
        from app.utils.streaming_parser import parse_json_array_stream_async

        response_text = ""
        raw_chunks = []

        async with self._client.stream("POST", url, json=payload, headers=headers) as response:
            # Check for errors
            if response.status_code != 200:
                error_text = await response.aread()
                logger.error(
                    f"Gemini API error: HTTP {response.status_code}\n"
                    f"Response: {error_text.decode()[:500]}"
                )
                response.raise_for_status()

            logger.debug(f"Received response from Gemini API: status={response.status_code}")

            # 逐块解析并收集
            async for chunk in parse_json_array_stream_async(response.aiter_lines()):
                raw_chunks.append(chunk)

                # 提取文本内容
                stream_assist = chunk.get("streamAssistResponse", {})
                answer = stream_assist.get("answer", {})
                replies = answer.get("replies", [])

                for reply in replies:
                    grounded_content = reply.get("groundedContent", {})
                    content = grounded_content.get("content", {})
                    text = content.get("text", "")
                    is_thought = content.get("thought", False)

                    # 跳过思考过程（thought: true），只保留实际答案
                    if text and not is_thought:
                        response_text += text

        logger.debug(f"[RESPONSE] Collected {len(raw_chunks)} chunks, total text length: {len(response_text)}")

        # 返回标准化的响应格式
        return {
            "response": response_text,
            "conversation_id": self._session_name,
            "raw_data": raw_chunks
        }

    async def upload_file(
        self,
        file_data: bytes,
        filename: str,
        mime_type: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Upload file to Gemini Business API

        Args:
            file_data: File content bytes
            filename: File name
            mime_type: MIME type (e.g., 'image/png', 'video/mp4')
            **kwargs: Additional request parameters

        Returns:
            dict: Upload response with file_id

        Raises:
            httpx.HTTPStatusError: On HTTP errors
            httpx.RequestError: On network errors
        """
        await self._ensure_client()

        # Get fresh token
        token = await self.account.token_manager.get_token()

        # Create session if needed
        if not self._session_name:
            self._session_name = await self._create_session()

        # Convert file to base64
        import base64
        base64_content = base64.b64encode(file_data).decode()

        # Build request payload
        payload = {
            "configId": self.account.team_id,
            "additionalParams": {"token": "-"},
            "addContextFileRequest": {
                "name": self._session_name,
                "fileName": filename,
                "mimeType": mime_type,
                "fileContents": base64_content
            }
        }

        # Send upload request
        url = f"{self.BASE_URL}{self.UPLOAD_API}"
        headers = self._get_headers(token)

        logger.debug(
            f"Uploading file to Gemini API: {filename} ({mime_type}, "
            f"{len(file_data)} bytes, account: {self.account.email})"
        )

        response = await self._client.post(
            url,
            json=payload,
            headers=headers,
        )

        # Check for errors
        response.raise_for_status()

        # Parse response
        result = response.json()
        file_id = result.get("addContextFileResponse", {}).get("fileId", "")

        logger.debug(f"File uploaded successfully: file_id={file_id}")

        return {
            "file_id": file_id,
            "filename": filename,
            "mime_type": mime_type
        }

    async def list_session_file_metadata(self, session_name: str) -> Dict[str, Dict[str, Any]]:
        """
        List AI-generated file metadata for a session.

        Returns:
            dict: Mapping of fileId -> metadata
        """
        await self._ensure_client()
        token = await self.account.token_manager.get_token()

        payload = {
            "configId": self.account.team_id,
            "additionalParams": {"token": "-"},
            "listSessionFileMetadataRequest": {
                "name": session_name,
                "filter": "file_origin_type = AI_GENERATED",
            },
        }

        url = f"{self.BASE_URL}{self.LIST_SESSION_FILES_API}"
        headers = self._get_headers(token)

        response = await self._client.post(url, json=payload, headers=headers)
        if response.status_code != 200:
            logger.warning(
                "Failed to list session file metadata: HTTP %s, body=%s",
                response.status_code,
                response.text[:200],
            )
            return {}

        data = response.json()
        file_metadata = data.get("listSessionFileMetadataResponse", {}).get("fileMetadata", [])
        result: Dict[str, Dict[str, Any]] = {}
        for item in file_metadata:
            file_id = item.get("fileId")
            if file_id:
                result[file_id] = item

        return result

    async def download_file(self, session_name: str, file_id: str) -> bytes:
        """
        Download a generated file from Gemini Business API.
        """
        await self._ensure_client()
        token = await self.account.token_manager.get_token()
        headers = self._get_headers(token)

        url = f"{self.BASE_URL}/{session_name}:downloadFile"
        params = {"fileId": file_id, "alt": "media"}
        response = await self._client.get(url, params=params, headers=headers)
        if response.status_code != 200:
            logger.error(
                "Failed to download file %s: HTTP %s, body=%s",
                file_id,
                response.status_code,
                response.text[:200],
            )
            response.raise_for_status()

        return response.content

    async def send_message_with_retry(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        max_retries: Optional[int] = None,
        stream: bool = False,
        **kwargs
    ):
        """
        Send message with automatic retry on transient errors

        Args:
            message: User message to send
            conversation_id: Optional conversation ID
            max_retries: Max retry attempts (default: MAX_RETRIES)
            stream: If True, return async generator; if False, return dict
            **kwargs: Additional request parameters

        Returns:
            AsyncIterator[str] (if stream=True) or dict (if stream=False)

        Raises:
            httpx.HTTPStatusError: On persistent HTTP errors
            httpx.RequestError: On persistent network errors
        """
        if max_retries is None:
            max_retries = self.MAX_RETRIES

        last_error = None

        for attempt in range(max_retries + 1):
            try:
                return await self.send_message(
                    message,
                    conversation_id=conversation_id,
                    stream=stream,
                    **kwargs
                )
            except httpx.HTTPStatusError as e:
                # Don't retry on client errors (4xx except 429)
                if 400 <= e.response.status_code < 500 and e.response.status_code != 429:
                    raise

                # 401 错误：清除缓存的 session，下次会创建新的
                if e.response.status_code == 401:
                    logger.warning("401 error, clearing cached session")
                    self._session_name = None

                last_error = e

                if attempt < max_retries:
                    logger.warning(
                        f"Request failed (attempt {attempt + 1}/{max_retries + 1}): "
                        f"status={e.response.status_code}, retrying..."
                    )

            except httpx.RequestError as e:
                last_error = e

                if attempt < max_retries:
                    logger.warning(
                        f"Network error (attempt {attempt + 1}/{max_retries + 1}): "
                        f"{type(e).__name__}, retrying..."
                    )

        # All retries failed
        logger.error(f"Request failed after {max_retries + 1} attempts")
        raise last_error

    def get_status_info(self) -> Dict[str, Any]:
        """
        Get client status information

        Returns:
            dict: Client status
        """
        return {
            "account_email": self.account.email,
            "account_team_id": self.account.team_id,
            "account_status": self.account.status.value,
            "client_initialized": self._client is not None,
            "has_session": self._session_name is not None,
            "base_url": self.BASE_URL,
        }
