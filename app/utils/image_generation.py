"""
Image generation helpers for Gemini Business API responses.
"""

from io import BytesIO
from typing import Any, Dict, List, Tuple

from PIL import Image


def parse_generated_files(raw_chunks: List[Dict[str, Any]]) -> Tuple[List[Dict[str, str]], str, str | None]:
    """
    Parse generated file references from Gemini stream chunks.

    Returns:
        (file_list, session_name, error_message)
        file_list: [{"fileId": str, "mimeType": str}, ...]
        session_name: session identifier if present
    """
    file_ids: List[Dict[str, str]] = []
    session_name = ""
    seen = set()
    error_message: str | None = None

    for chunk in raw_chunks:
        if "error" in chunk and not error_message:
            err = chunk.get("error", {})
            error_message = err.get("message") or str(err)

        stream_assist = chunk.get("streamAssistResponse", {})
        session_info = stream_assist.get("sessionInfo", {})
        if session_info.get("session"):
            session_name = session_info["session"]

        answer = stream_assist.get("answer", {})
        replies = answer.get("replies", [])

        for reply in replies:
            grounded_content = reply.get("groundedContent", {})
            content = grounded_content.get("content", {})
            file_info = content.get("file")
            if not file_info:
                continue

            file_id = file_info.get("fileId")
            if not file_id or file_id in seen:
                continue

            seen.add(file_id)
            file_ids.append({
                "fileId": file_id,
                "mimeType": file_info.get("mimeType", "image/png"),
            })

    return file_ids, session_name, error_message


def extract_image_metadata(image_bytes: bytes, mime_type: str) -> Dict[str, Any]:
    """
    Extract image metadata from bytes.
    """
    with Image.open(BytesIO(image_bytes)) as img:
        width, height = img.size

    return {
        "mime_type": mime_type,
        "width": width,
        "height": height,
    }
