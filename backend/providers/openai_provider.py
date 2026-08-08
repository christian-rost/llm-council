"""OpenAI-compatible provider — works for OpenAI, xAI (Grok), Mistral."""

import logging
import httpx
from typing import List, Dict, Any, Optional

from .base import PROVIDER_CONFIGS, ProviderError, format_exception, format_http_error

logger = logging.getLogger(__name__)


async def query(
    model: str,
    messages: List[Dict[str, Any]],
    api_key: str,
    provider: str = "openai",
    timeout: float = 120.0,
    pdf_data: Optional[str] = None,
    pdf_filename: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Query via OpenAI-compatible chat/completions endpoint."""
    base_url = PROVIDER_CONFIGS[provider]["base_url"]

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # Convert messages, adding PDF to last user message
    formatted_messages = []
    for i, msg in enumerate(messages):
        if msg["role"] == "user" and pdf_data and i == len(messages) - 1:
            filename = pdf_filename or "document.pdf"
            if provider == "openai":
                # OpenAI Chat Completions: "file" content type
                content = [
                    {
                        "type": "file",
                        "file": {
                            "filename": filename,
                            "file_data": f"data:application/pdf;base64,{pdf_data}",
                        },
                    },
                    {"type": "text", "text": msg["content"]},
                ]
            else:
                # xAI, Mistral: image_url fallback
                content = [
                    {"type": "text", "text": msg["content"]},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:application/pdf;base64,{pdf_data}",
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

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(base_url, headers=headers, json=payload)
            if response.is_error:
                raise ProviderError(format_http_error(response.status_code, response.text))
            data = response.json()

            message = data["choices"][0]["message"]

            # Extract usage data
            usage = data.get("usage", {})
            prompt_tokens_details = usage.get("prompt_tokens_details", {})

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
        logger.error(f"{provider} error for {model}: {e}")
        raise
    except Exception as e:
        logger.error(f"{provider} error for {model}: {e}")
        raise ProviderError(format_exception(e)) from e
