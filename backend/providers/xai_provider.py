"""Responses API provider — used for web_search with OpenAI and xAI.

Both OpenAI and xAI support the Responses API (/v1/responses) with a
web_search tool. Without web_search, these providers use the
OpenAI-compatible chat/completions endpoint (openai_provider.py).
"""

import logging
import httpx
from typing import List, Dict, Any, Optional

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
        logger.error(f"No Responses API URL configured for provider '{provider}'")
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # Convert messages to the Responses API input format
    input_messages = []
    for msg in messages:
        input_messages.append({
            "role": msg["role"],
            "content": msg["content"],
        })

    payload = {
        "model": model,
        "input": input_messages,
        "tools": [{"type": "web_search"}],
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

            # Extract text from output items
            text_parts = []
            for item in data.get("output", []):
                if item.get("type") == "message":
                    for block in item.get("content", []):
                        if block.get("type") == "output_text":
                            text_parts.append(block.get("text", ""))

            content = "\n".join(text_parts) if text_parts else None

            return {
                "content": content,
                "reasoning_details": None,
            }
    except Exception as e:
        logger.error(f"{provider} Responses API error for {model}: {e}")
        return None
