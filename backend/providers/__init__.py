"""Provider registry and dispatcher for multi-provider LLM support."""

import asyncio
import logging
import os
from typing import Dict, List, Any, Optional, Tuple

from .base import PROVIDER_CONFIGS, ProviderError, format_exception
from . import openrouter, openai_provider, anthropic_provider, google_provider, xai_provider

logger = logging.getLogger(__name__)


def parse_model_id(model_id: str) -> tuple[str, str]:
    """Parse a model ID into (provider, bare_model).

    Formats:
        "provider:model"              → ("provider", "model")
        "vendor/model"                → ("openrouter", "vendor/model")
        "vendor/model:online"         → ("openrouter", "vendor/model:online")  # OpenRouter suffix
    """
    if ":" in model_id:
        provider, bare_model = model_id.split(":", 1)
        if provider in PROVIDER_CONFIGS:
            return provider, bare_model
    # Legacy format or OpenRouter with suffixes (e.g. "openai/gpt-5.1:online")
    return "openrouter", model_id


def get_api_key(provider: str) -> str | None:
    """Get the API key for a provider.

    Priority: DB (encrypted) > Environment variable.
    """
    # Try DB first (lazy import to avoid circular deps)
    try:
        from ..settings import get_provider_api_key
        db_key = get_provider_api_key(provider)
        if db_key:
            return db_key
    except Exception:
        pass

    # Fallback to environment variable
    config = PROVIDER_CONFIGS.get(provider)
    if config:
        return os.getenv(config["env_var"])
    return None


async def query_model_result(
    model_id: str,
    messages: List[Dict[str, Any]],
    timeout: float = 120.0,
    pdf_data: Optional[str] = None,
    pdf_filename: Optional[str] = None,
    web_search: bool = False,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Query a model and return (response, error_reason).

    On success the reason is None; on failure the response is None and the
    reason is a short, user-safe explanation (HTTP status + provider message,
    timeout, empty response, ...).
    """
    provider, _ = parse_model_id(model_id)

    try:
        response = await _dispatch(
            model_id, messages,
            timeout=timeout, pdf_data=pdf_data, pdf_filename=pdf_filename,
            web_search=web_search,
        )
    except ProviderError as e:
        return None, str(e)
    except Exception as e:
        logger.error(f"Unexpected error querying {model_id}: {e}")
        return None, format_exception(e)

    if response is None:
        return None, f"No response from provider '{provider}'"

    if not (response.get("content") or "").strip():
        logger.error(f"{model_id} returned an empty response")
        return None, "Model returned an empty response"

    return response, None


async def query_model(
    model_id: str,
    messages: List[Dict[str, Any]],
    timeout: float = 120.0,
    pdf_data: Optional[str] = None,
    pdf_filename: Optional[str] = None,
    web_search: bool = False,
) -> Optional[Dict[str, Any]]:
    """Dispatch a query to the correct provider based on model_id.

    This is the main entry point — drop-in replacement for openrouter.query_model().
    Returns None on failure; use query_model_result() to get the reason.
    """
    response, _error = await query_model_result(
        model_id, messages,
        timeout=timeout, pdf_data=pdf_data, pdf_filename=pdf_filename,
        web_search=web_search,
    )
    return response


async def _dispatch(
    model_id: str,
    messages: List[Dict[str, Any]],
    timeout: float = 120.0,
    pdf_data: Optional[str] = None,
    pdf_filename: Optional[str] = None,
    web_search: bool = False,
) -> Optional[Dict[str, Any]]:
    """Route the query to the provider handler. Raises ProviderError on failure."""
    provider, bare_model = parse_model_id(model_id)
    api_key = get_api_key(provider)

    if not api_key:
        raise ProviderError(f"No API key configured for provider '{provider}'")

    if provider == "openrouter":
        return await openrouter.query(
            bare_model, messages, api_key,
            timeout=timeout, pdf_data=pdf_data, pdf_filename=pdf_filename,
            web_search=web_search,
        )
    elif provider in ("openai", "xai") and web_search:
        # OpenAI + xAI web search requires the Responses API (/v1/responses)
        return await xai_provider.query(
            bare_model, messages, api_key, provider=provider,
            timeout=timeout, pdf_data=pdf_data, pdf_filename=pdf_filename,
        )
    elif provider in ("openai", "xai", "mistral"):
        return await openai_provider.query(
            bare_model, messages, api_key, provider=provider,
            timeout=timeout, pdf_data=pdf_data, pdf_filename=pdf_filename,
        )
    elif provider == "anthropic":
        return await anthropic_provider.query(
            bare_model, messages, api_key,
            timeout=timeout, pdf_data=pdf_data, pdf_filename=pdf_filename,
            web_search=web_search,
        )
    elif provider == "google":
        return await google_provider.query(
            bare_model, messages, api_key,
            timeout=timeout, pdf_data=pdf_data, pdf_filename=pdf_filename,
            web_search=web_search,
        )
    else:
        raise ProviderError(f"Unknown provider '{provider}'")


async def query_models_parallel(
    models: List[str],
    messages: List[Dict[str, Any]],
    pdf_data: Optional[str] = None,
    pdf_filename: Optional[str] = None,
    web_search: bool = False,
) -> Dict[str, Optional[Dict[str, Any]]]:
    """Query multiple models in parallel via their respective providers."""
    tasks = [
        query_model(model, messages, pdf_data=pdf_data, pdf_filename=pdf_filename, web_search=web_search)
        for model in models
    ]
    responses = await asyncio.gather(*tasks)
    return {model: response for model, response in zip(models, responses)}
