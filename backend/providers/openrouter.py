"""OpenRouter provider — extracted from backend/openrouter.py."""

import logging
import httpx
from typing import List, Dict, Any, Optional

from .base import ProviderError, format_exception, format_http_error

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


async def query(
    model: str,
    messages: List[Dict[str, Any]],
    api_key: str,
    timeout: float = 120.0,
    pdf_data: Optional[str] = None,
    pdf_filename: Optional[str] = None,
    web_search: bool = False,
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

    # Append :online suffix for web search (if not already present)
    effective_model = model
    if web_search and not model.endswith(":online"):
        effective_model = f"{model}:online"

    payload = {
        "model": effective_model,
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
            if response.is_error:
                raise ProviderError(format_http_error(response.status_code, response.text))
            data = response.json()

            message = data["choices"][0]["message"]

            # Extract usage data
            usage = data.get("usage", {})
            prompt_tokens_details = usage.get("prompt_tokens_details", {}) or {}

            return {
                "content": message.get("content"),
                "reasoning_details": message.get("reasoning_details"),
                "usage": {
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                    "cached_tokens": prompt_tokens_details.get("cached_tokens", 0),
                }
            }
    except ProviderError as e:
        logger.error(f"OpenRouter error for {model}: {e}")
        raise
    except Exception as e:
        logger.error(f"OpenRouter error for {model}: {e}")
        raise ProviderError(format_exception(e)) from e
