"""
Chat Routes - API endpoints for Gemini chat functionality

Provides endpoints for:
- Text chat with Gemini Business
- File uploads (images/videos)
- Conversation management
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field

from app.core.account_pool import AccountPool
from app.core.gemini_client import GeminiClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

# Global account pool (initialized on startup)
account_pool: Optional[AccountPool] = None


def set_account_pool(pool: AccountPool) -> None:
    """
    Set the global account pool instance

    Args:
        pool: AccountPool instance
    """
    global account_pool
    account_pool = pool


# Request/Response Models
class ChatRequest(BaseModel):
    """Chat request model"""

    message: str = Field(..., min_length=1, max_length=10000, description="User message")
    conversation_id: Optional[str] = Field(None, description="Conversation ID for context")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="Response randomness")
    max_tokens: Optional[int] = Field(None, ge=1, le=8192, description="Max response tokens")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "message": "Hello, can you help me?",
                    "conversation_id": "conv-123",
                    "temperature": 0.7,
                }
            ]
        }
    }


class ChatResponse(BaseModel):
    """Chat response model"""

    response: str = Field(..., description="Gemini's response")
    conversation_id: str = Field(..., description="Conversation ID")
    account_email: str = Field(..., description="Account used for request")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "response": "Hello! I'd be happy to help you.",
                    "conversation_id": "conv-123",
                    "account_email": "user@example.com",
                }
            ]
        }
    }


class UploadResponse(BaseModel):
    """File upload response model"""

    file_id: str = Field(..., description="Uploaded file ID")
    filename: str = Field(..., description="Original filename")
    mime_type: str = Field(..., description="File MIME type")
    account_email: str = Field(..., description="Account used for upload")


@router.post("/send", response_model=ChatResponse)
async def send_message(request: ChatRequest) -> ChatResponse:
    """
    Send message to Gemini Business

    Args:
        request: Chat request with message and optional parameters

    Returns:
        ChatResponse: Gemini's response with conversation ID

    Raises:
        HTTPException: On errors (503 if no accounts available, 500 on API errors)
    """
    if account_pool is None:
        raise HTTPException(
            status_code=503,
            detail="Service unavailable: Account pool not initialized",
        )

    # Get available account from pool
    try:
        account = await account_pool.get_available_account()
    except Exception as e:
        logger.error(f"Failed to get available account: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"No available accounts: {str(e)}",
        )

    # Send message using GeminiClient
    try:
        async with GeminiClient(account) as client:
            # Build request parameters
            kwargs = {}
            if request.temperature is not None:
                kwargs["temperature"] = request.temperature
            if request.max_tokens is not None:
                kwargs["max_tokens"] = request.max_tokens

            # Send with retry
            result = await client.send_message_with_retry(
                message=request.message,
                conversation_id=request.conversation_id,
                **kwargs,
            )

            logger.info(
                f"Message sent successfully: "
                f"account={account.email}, "
                f"conversation_id={result.get('conversation_id', 'N/A')}"
            )

            return ChatResponse(
                response=result.get("response", ""),
                conversation_id=result.get("conversation_id", ""),
                account_email=account.email,
            )

    except Exception as e:
        # Determine error type and set cooldown if needed
        if hasattr(e, "response"):
            status_code = e.response.status_code
            error_message = str(e)

            # Handle account-level errors
            account_pool.handle_error(account, status_code, error_message)

            # Return appropriate HTTP error
            if status_code in [401, 403]:
                raise HTTPException(
                    status_code=status_code,
                    detail=f"Authentication failed: {error_message}",
                )
            elif status_code == 429:
                raise HTTPException(
                    status_code=status_code,
                    detail="Rate limit exceeded. Please try again later.",
                )
            else:
                raise HTTPException(
                    status_code=status_code,
                    detail=f"API error: {error_message}",
                )
        else:
            # Network or other error
            logger.error(f"Unexpected error sending message: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Internal server error: {str(e)}",
            )


@router.post("/upload", response_model=UploadResponse)
async def upload_file(
    file: UploadFile = File(..., description="File to upload (image or video)"),
) -> UploadResponse:
    """
    Upload file to Gemini Business

    Supports images (PNG, JPEG, GIF, WebP) and videos (MP4, MOV, AVI).

    Args:
        file: Uploaded file

    Returns:
        UploadResponse: Upload result with file_id

    Raises:
        HTTPException: On errors (400 for invalid files, 503 if no accounts)
    """
    if account_pool is None:
        raise HTTPException(
            status_code=503,
            detail="Service unavailable: Account pool not initialized",
        )

    # Validate file type
    allowed_types = {
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
        "video/mp4",
        "video/quicktime",
        "video/x-msvideo",
    }

    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}. "
            f"Allowed types: {', '.join(allowed_types)}",
        )

    # Get available account
    try:
        account = await account_pool.get_available_account()
    except Exception as e:
        logger.error(f"Failed to get available account: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"No available accounts: {str(e)}",
        )

    # Read file data
    try:
        file_data = await file.read()

        # Validate file size (max 20MB)
        max_size = 20 * 1024 * 1024  # 20MB
        if len(file_data) > max_size:
            raise HTTPException(
                status_code=400,
                detail=f"File too large: {len(file_data)} bytes (max: {max_size})",
            )

    except Exception as e:
        logger.error(f"Failed to read file: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to read file: {str(e)}",
        )

    # Upload file
    try:
        async with GeminiClient(account) as client:
            result = await client.upload_file(
                file_data=file_data,
                filename=file.filename or "upload",
                mime_type=file.content_type,
            )

            logger.info(
                f"File uploaded successfully: "
                f"filename={file.filename}, "
                f"size={len(file_data)}, "
                f"account={account.email}"
            )

            return UploadResponse(
                file_id=result.get("file_id", ""),
                filename=file.filename or "upload",
                mime_type=file.content_type,
                account_email=account.email,
            )

    except Exception as e:
        # Handle errors similar to send_message
        if hasattr(e, "response"):
            status_code = e.response.status_code
            error_message = str(e)

            account_pool.handle_error(account, status_code, error_message)

            raise HTTPException(
                status_code=status_code,
                detail=f"Upload failed: {error_message}",
            )
        else:
            logger.error(f"Unexpected error uploading file: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Internal server error: {str(e)}",
            )
