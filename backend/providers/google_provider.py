"""Google Gemini generateContent provider."""

import logging
import httpx
from typing import List, Dict, Any, Optional

from .base import PROVIDER_CONFIGS

logger = logging.getLogger(__name__)


async def query(
    model: str,
    messages: List[Dict[str, Any]],
    api_key: str,
    timeout: float = 120.0,
    pdf_data: Optional[str] = None,
    pdf_filename: Optional[str] = None,
    web_search: bool = False,
) -> Optional[Dict[str, Any]]:
    """Query via Google Gemini generateContent API."""
    base_url = PROVIDER_CONFIGS["google"]["base_url"]
    url = f"{base_url}/models/{model}:generateContent?key={api_key}"

    # Convert messages to Gemini contents format
    # Gemini uses "user" and "model" roles (not "assistant")
    contents = []
    system_instruction = None

    for msg in messages:
        role = msg["role"]
        if role == "system":
            system_instruction = msg["content"]
            continue

        gemini_role = "model" if role == "assistant" else "user"
        parts = []

        # Add PDF as inline_data to last user message
        if role == "user" and pdf_data and msg is messages[-1]:
            parts.append({
                "inline_data": {
                    "mime_type": "application/pdf",
                    "data": pdf_data,
                }
            })

        parts.append({"text": msg["content"]})
        contents.append({"role": gemini_role, "parts": parts})

    payload = {"contents": contents}

    if web_search:
        payload["tools"] = [{"google_search": {}}]

    if system_instruction:
        payload["systemInstruction"] = {
            "parts": [{"text": system_instruction}]
        }

    logger.info(f"Google for {model}: web_search={'YES' if web_search else 'NO'}")

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            # Extract text from candidates[0].content.parts
            candidates = data.get("candidates", [])
            if not candidates:
                logger.error(f"Gemini: no candidates in response for {model}")
                return None

            parts = candidates[0].get("content", {}).get("parts", [])
            text_parts = [p.get("text", "") for p in parts if "text" in p]
            return {
                "content": "\n".join(text_parts),
                "reasoning_details": None,
            }
    except Exception as e:
        logger.error(f"Google error for {model}: {e}")
        return None
