"""Responses API provider — used for web_search with OpenAI and xAI.

Both OpenAI and xAI support the Responses API (/v1/responses) with a
web_search tool. Without web_search, these providers use the
OpenAI-compatible chat/completions endpoint (openai_provider.py).
"""

import logging
import httpx
from typing import List, Dict, Any, Optional

from .base import ProviderError, format_exception, format_http_error

logger = logging.getLogger(__name__)

# Responses API endpoints per provider
RESPONSES_URLS = {
    "xai": "https://api.x.ai/v1/responses",
    "openai": "https://api.openai.com/v1/responses",
}


async def query(
    model: str,
    messages: List[Dict[str, Any]],
    api_key: str,
    provider: str = "xai",
    timeout: float = 120.0,
    pdf_data: Optional[str] = None,
    pdf_filename: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Query via Responses API with web_search tool."""
    url = RESPONSES_URLS.get(provider)
    if not url:
        raise ProviderError(f"No Responses API URL configured for provider '{provider}'")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # Convert messages to the Responses API input format (messages array)
    input_messages = []
    for i, m in enumerate(messages):
        if m["role"] == "user" and pdf_data and i == len(messages) - 1:
            filename = pdf_filename or "document.pdf"
            content = [
                {
                    "type": "input_file",
                    "filename": filename,
                    "file_data": f"data:application/pdf;base64,{pdf_data}",
                },
                {"type": "input_text", "text": m["content"]},
            ]
            input_messages.append({"role": m["role"], "content": content})
        else:
            input_messages.append({"role": m["role"], "content": m["content"]})

    payload = {
        "model": model,
        "input": input_messages,
        "tools": [{"type": "web_search"}],
        "tool_choice": "required",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
            if not response.is_success:
                raise ProviderError(format_http_error(response.status_code, response.text))
            data = response.json()

            # Check if web search was actually invoked
            output_types = [item.get("type") for item in data.get("output", [])]
            search_performed = "web_search_call" in output_types
            logger.info(
                f"{provider} Responses API for {model}: "
                f"web_search={'YES' if search_performed else 'NO'}"
            )

            # Extract text from output items
            text_parts = []
            for item in data.get("output", []):
                if item.get("type") == "message":
                    for block in item.get("content", []):
                        if block.get("type") == "output_text":
                            text_parts.append(block.get("text", ""))

            content = "\n".join(text_parts) if text_parts else None

            # Extract usage data from usage field
            usage = data.get("usage", {})
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)

            return {
                "content": content,
                "reasoning_details": None,
                "usage": {
                    "prompt_tokens": input_tokens,
                    "completion_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                    "cached_tokens": 0,  # Responses API doesn't expose cached tokens
                }
            }
    except ProviderError as e:
        logger.error(f"{provider} Responses API error for {model}: {e}")
        raise
    except Exception as e:
        logger.error(f"{provider} Responses API error for {model}: {e}")
        raise ProviderError(format_exception(e)) from e
