"""Anthropic Messages API provider."""

import logging
import httpx
from typing import List, Dict, Any, Optional

from .base import ProviderError, format_exception, format_http_error

logger = logging.getLogger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


async def query(
    model: str,
    messages: List[Dict[str, Any]],
    api_key: str,
    timeout: float = 120.0,
    pdf_data: Optional[str] = None,
    pdf_filename: Optional[str] = None,
    web_search: bool = False,
) -> Optional[Dict[str, Any]]:
    """Query via Anthropic Messages API."""
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }

    # Extract system messages separately (Anthropic uses a top-level system param)
    system_parts = []
    non_system_messages = []
    for msg in messages:
        if msg["role"] == "system":
            system_parts.append(msg["content"])
        else:
            non_system_messages.append(msg)

    # Convert messages, adding PDF as document block to last user message
    formatted_messages = []
    for i, msg in enumerate(non_system_messages):
        if msg["role"] == "user" and pdf_data and i == len(non_system_messages) - 1:
            content = [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": pdf_data,
                    },
                },
                {"type": "text", "text": msg["content"]},
            ]
            formatted_messages.append({"role": msg["role"], "content": content})
        else:
            formatted_messages.append(msg)

    payload = {
        "model": model,
        "messages": formatted_messages,
        "max_tokens": 8192,
    }

    if system_parts:
        payload["system"] = "\n\n".join(system_parts)

    if web_search:
        payload["tools"] = [{"type": "web_search_20250305", "name": "web_search"}]

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(ANTHROPIC_URL, headers=headers, json=payload)
            if response.is_error:
                raise ProviderError(format_http_error(response.status_code, response.text))
            data = response.json()

            # Handle pause_turn: continue the conversation to get full response
            if data.get("stop_reason") == "pause_turn":
                continued_messages = formatted_messages + [
                    {"role": "assistant", "content": data.get("content", [])}
                ]
                cont_payload = {**payload, "messages": continued_messages}
                response = await client.post(ANTHROPIC_URL, headers=headers, json=cont_payload)
                if response.is_error:
                    raise ProviderError(format_http_error(response.status_code, response.text))
                data = response.json()

            # Anthropic returns content as a list of blocks
            content_blocks = data.get("content", [])
            text_parts = [
                block.get("text", "")
                for block in content_blocks
                if block.get("type") == "text"
            ]

            if web_search:
                search_performed = any(
                    block.get("type") == "server_tool_use" and block.get("name") == "web_search"
                    for block in content_blocks
                )
                logger.info(
                    f"Anthropic for {model}: "
                    f"web_search={'YES' if search_performed else 'NO'}"
                )

            # Extract usage data
            usage = data.get("usage", {})

            return {
                "content": "\n".join(text_parts),
                "reasoning_details": None,
                "usage": {
                    "prompt_tokens": usage.get("input_tokens", 0),
                    "completion_tokens": usage.get("output_tokens", 0),
                    "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
                    "cached_tokens": usage.get("cache_read_input_tokens", 0),
                }
            }
    except ProviderError as e:
        logger.error(f"Anthropic error for {model}: {e}")
        raise
    except Exception as e:
        logger.error(f"Anthropic error for {model}: {e}")
        raise ProviderError(format_exception(e)) from e
