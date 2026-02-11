"""xAI Responses API provider — used when web_search is enabled.

Without web_search, xAI uses the OpenAI-compatible chat/completions endpoint
(handled by openai_provider.py). With web_search, xAI requires the newer
/v1/responses endpoint with a web_search tool.
"""

import logging
import httpx
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

XAI_RESPONSES_URL = "https://api.x.ai/v1/responses"


async def query(
    model: str,
    messages: List[Dict[str, Any]],
    api_key: str,
    timeout: float = 120.0,
    pdf_data: Optional[str] = None,
    pdf_filename: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Query via xAI Responses API with web_search tool."""
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
            response = await client.post(XAI_RESPONSES_URL, headers=headers, json=payload)
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
        logger.error(f"xAI Responses API error for {model}: {e}")
        return None
