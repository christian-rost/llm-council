"""
OpenRouter API client with PDF support.
"""

import httpx
from typing import Optional, List, Dict, Any

from .config import OPENROUTER_API_KEY, OPENROUTER_API_URL


async def query_model(
    model: str,
    messages: List[Dict[str, Any]],
    pdf_data: Optional[str] = None,
    pdf_filename: Optional[str] = None
) -> str:
    """
    Query a model via OpenRouter API.
    
    Args:
        model: The model identifier (e.g., "openai/gpt-4")
        messages: List of message dicts with role and content
        pdf_data: Optional base64-encoded PDF data
        pdf_filename: Optional filename for the PDF
    
    Returns:
        The model's response text
    """
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY not set")
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://llm-council.xqtfive.de",
        "X-Title": "LLM Council"
    }
    
    # Convert messages to OpenRouter format, adding PDF if present
    formatted_messages = []
    for msg in messages:
        if msg["role"] == "user" and pdf_data and msg == messages[-1]:
            # Add PDF to the last user message
            content = [
                {
                    "type": "text",
                    "text": msg["content"]
                },
                {
                    "type": "file",
                    "file": {
                        "filename": pdf_filename or "document.pdf",
                        "file_data": f"data:application/pdf;base64,{pdf_data}"
                    }
                }
            ]
            formatted_messages.append({
                "role": msg["role"],
                "content": content
            })
        else:
            formatted_messages.append(msg)
    
    payload = {
        "model": model,
        "messages": formatted_messages,
    }
    
    # Add PDF parsing plugin configuration (use free pdf-text engine)
    if pdf_data:
        payload["plugins"] = [
            {
                "id": "file-parser",
                "pdf": {
                    "engine": "pdf-text"  # Free engine, use "mistral-ocr" for scanned docs
                }
            }
        ]
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            OPENROUTER_API_URL,
            headers=headers,
            json=payload
        )
        
        if response.status_code != 200:
            error_detail = response.text
            raise Exception(f"OpenRouter API error ({response.status_code}): {error_detail}")
        
        data = response.json()
        
        if "choices" not in data or len(data["choices"]) == 0:
            raise Exception("No response from model")
        
        return data["choices"][0]["message"]["content"]


async def query_model_simple(model: str, prompt: str) -> str:
    """
    Simple query without PDF support (for titles, rankings, etc.)
    """
    messages = [{"role": "user", "content": prompt}]
    return await query_model(model, messages)
