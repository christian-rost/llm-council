"""OpenRouter provider — extracted from backend/openrouter.py."""

import logging
import httpx
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


async def query(
    model: str,
    messages: List[Dict[str, Any]],
    api_key: str,
    timeout: float = 120.0,
    pdf_data: Optional[str] = None,
    pdf_filename: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Query a model via OpenRouter API."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # Convert messages to OpenRouter format, adding PDF if present
    formatted_messages = []
    for i, msg in enumerate(messages):
        if msg["role"] == "user" and pdf_data and i == len(messages) - 1:
            content = [
                {"type": "text", "text": msg["content"]},
                {
                    "type": "file",
                    "file": {
                        "filename": pdf_filename or "document.pdf",
                        "file_data": f"data:application/pdf;base64,{pdf_data}",
                    },
                },
            ]
            formatted_messages.append({"role": msg["role"], "content": content})
        else:
            formatted_messages.append(msg)

    payload = {
        "model": model,
        "messages": formatted_messages,
    }

    if pdf_data:
        payload["plugins"] = [
            {
                "id": "file-parser",
                "pdf": {"engine": "pdf-text"},
            }
        ]

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(OPENROUTER_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

            message = data["choices"][0]["message"]
            return {
                "content": message.get("content"),
                "reasoning_details": message.get("reasoning_details"),
            }
    except Exception as e:
        logger.error(f"OpenRouter error for {model}: {e}")
        return None
