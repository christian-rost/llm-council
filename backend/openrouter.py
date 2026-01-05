"""OpenRouter API client for making LLM requests with PDF support."""

import httpx
from typing import List, Dict, Any, Optional

from .config import OPENROUTER_API_KEY, OPENROUTER_API_URL


async def query_model(
    model: str,
    messages: List[Dict[str, Any]],
    timeout: float = 120.0,
    pdf_data: Optional[str] = None,
    pdf_filename: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Query a single model via OpenRouter API.
    
    Args:
        model: OpenRouter model identifier (e.g., "openai/gpt-4o")
        messages: List of message dicts with 'role' and 'content'
        timeout: Request timeout in seconds
        pdf_data: Optional base64-encoded PDF data
        pdf_filename: Optional filename for the PDF
    
    Returns:
        Response dict with 'content' and optional 'reasoning_details', or None if failed
    """
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    
    # Convert messages to OpenRouter format, adding PDF if present
    formatted_messages = []
    for i, msg in enumerate(messages):
        # Add PDF to the last user message
        if msg["role"] == "user" and pdf_data and i == len(messages) - 1:
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
    
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            
            message = data['choices'][0]['message']
            return {
                'content': message.get('content'),
                'reasoning_details': message.get('reasoning_details')
            }
    except Exception as e:
        print(f"Error querying model {model}: {e}")
        return None


async def query_models_parallel(
    models: List[str],
    messages: List[Dict[str, Any]],
    pdf_data: Optional[str] = None,
    pdf_filename: Optional[str] = None
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Query multiple models in parallel.
    
    Args:
        models: List of OpenRouter model identifiers
        messages: List of message dicts to send to each model
        pdf_data: Optional base64-encoded PDF data
        pdf_filename: Optional filename for the PDF
    
    Returns:
        Dict mapping model identifier to response dict (or None if failed)
    """
    import asyncio
    
    # Create tasks for all models
    tasks = [
        query_model(model, messages, pdf_data=pdf_data, pdf_filename=pdf_filename) 
        for model in models
    ]
    
    # Wait for all to complete
    responses = await asyncio.gather(*tasks)
    
    # Map models to their responses
    return {model: response for model, response in zip(models, responses)}
