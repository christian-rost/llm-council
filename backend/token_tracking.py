"""Token usage tracking and cost estimation for XQT5AIs."""

import logging
import re
from typing import Dict, Any, Optional
from decimal import Decimal

from .database import supabase

logger = logging.getLogger(__name__)

# Prices per 1M tokens (can be overridden via app_settings)
DEFAULT_PRICING = {
    "openai": {
        "gpt-5.1": {"input": 2.00, "output": 10.00, "cached": 0.50},
        "gpt-4.1": {"input": 2.00, "output": 8.00, "cached": 0.50},
        "gpt-4.1-nano": {"input": 0.10, "output": 0.40, "cached": 0.025},
    },
    "anthropic": {
        "claude-sonnet-4.5": {"input": 3.00, "output": 15.00, "cached": 0.30},
        "claude-haiku-4-5": {"input": 0.80, "output": 4.00, "cached": 0.08},
    },
    "google": {
        "gemini-3-pro-preview": {"input": 1.25, "output": 10.00, "cached": 0.00},
        "gemini-2.5-flash": {"input": 0.15, "output": 0.60, "cached": 0.00},
    },
    "xai": {
        "grok-4": {"input": 5.00, "output": 15.00, "cached": 0.00},
        "grok-3-mini-fast": {"input": 0.60, "output": 4.00, "cached": 0.00},
    },
    "mistral": {
        "mistral-large-latest": {"input": 2.00, "output": 6.00, "cached": 0.00},
        "mistral-small-latest": {"input": 0.20, "output": 0.60, "cached": 0.00},
    },
}


def normalize_model_name(model: str) -> str:
    """Normalize model name for pricing lookup."""
    # Remove date/version suffixes like -20251001 or -latest
    base = model.split(":")[-1]  # Get the part after provider:
    base = base.split("/")[-1]   # Get the part after any vendor/

    # Remove common version/date suffixes
    # Remove date suffixes like -20251001 or -latest
    base = re.sub(r'-[0-9]{8}$', '', base)
    base = re.sub(r'-latest$', '', base)
    base = re.sub(r'-fast$', '', base)

    return base.lower()


def get_pricing_for_model(provider: str, model: str) -> Optional[Dict[str, float]]:
    """Get pricing for a specific model, with fallback to similar models."""
    provider_pricing = DEFAULT_PRICING.get(provider, {})

    if not provider_pricing:
        return None

    # Try exact match first
    if model in provider_pricing:
        return provider_pricing[model]

    # Try normalized name
    normalized = normalize_model_name(model)
    if normalized in provider_pricing:
        return provider_pricing[normalized]

    # Try partial match (e.g., "gpt-4.1-turbo" matches "gpt-4.1")
    for price_key, pricing in sorted(provider_pricing.items(), key=lambda x: len(x[0]), reverse=True):
        if price_key in normalized or normalized.startswith(price_key):
            return pricing

    # Fallback: use the cheapest model from this provider
    if provider_pricing:
        cheapest = min(provider_pricing.items(), key=lambda x: x[1]["input"] + x[1]["output"])
        logger.warning(f"No exact pricing for {provider}/{model}, using fallback {cheapest[0]}")
        return cheapest[1]

    return None


def calculate_cost(
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cached_tokens: int = 0
) -> Decimal:
    """Calculate estimated cost in USD.

    Formula:
        input_cost = (prompt_tokens - cached_tokens) * input_price_per_1m / 1_000_000
                   + cached_tokens * cached_price_per_1m / 1_000_000
        output_cost = completion_tokens * output_price_per_1m / 1_000_000
        total = input_cost + output_cost
    """
    pricing = get_pricing_for_model(provider, model)

    if not pricing:
        logger.warning(f"No pricing found for {provider}/{model}, cost will be 0")
        return Decimal("0")

    input_price = pricing.get("input", 0)
    output_price = pricing.get("output", 0)
    cached_price = pricing.get("cached", 0)

    # Calculate costs per formula
    non_cached_prompt = max(0, prompt_tokens - cached_tokens)

    input_cost = (non_cached_prompt * input_price / 1_000_000)
    if cached_tokens > 0 and cached_price > 0:
        input_cost += (cached_tokens * cached_price / 1_000_000)

    output_cost = (completion_tokens * output_price / 1_000_000)

    total = Decimal(str(input_cost + output_cost)).quantize(Decimal("0.000001"))

    return total


def store_usage(
    conversation_id: Optional[str],
    message_id: Optional[str],
    model: str,
    provider: str,
    stage: str,
    usage: Dict[str, Any],
    source: str = 'chat',
    api_key_id: Optional[str] = None,
) -> None:
    """Store token usage in database."""
    try:
        # uses module-level supabase singleton

        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0) or (prompt_tokens + completion_tokens)
        cached_tokens = usage.get("cached_tokens", 0)

        # Calculate estimated cost
        estimated_cost = calculate_cost(
            provider, model, prompt_tokens, completion_tokens, cached_tokens
        )

        data = {
            "model": model,
            "provider": provider,
            "stage": stage,
            "source": source,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cached_tokens": cached_tokens,
            "estimated_cost_usd": float(estimated_cost) if estimated_cost else None,
        }

        if conversation_id:
            data["conversation_id"] = conversation_id
        if message_id:
            data["message_id"] = message_id
        if api_key_id:
            data["api_key_id"] = api_key_id

        supabase.table("token_usage").insert(data).execute()

    except Exception as e:
        logger.error(f"Failed to store token usage: {e}")
        # Don't raise - token tracking should not break the main flow


def store_usage_from_response(
    conversation_id: Optional[str],
    message_id: Optional[str],
    model_id: str,
    stage: str,
    response: Optional[Dict[str, Any]],
    source: str = 'chat',
    api_key_id: Optional[str] = None,
) -> None:
    """Store usage from a provider response.

    Args:
        conversation_id: The conversation ID (None for API calls)
        message_id: The message ID (None for API calls)
        model_id: Full model ID (e.g., "openai:gpt-4.1")
        stage: Stage name (stage1, stage2, stage3, title)
        response: The provider response dict (may contain 'usage' key)
        source: 'chat' or 'api'
        api_key_id: API key ID for public API calls
    """
    if not response:
        return

    usage = response.get("usage")
    if not usage:
        return

    # Parse provider from model_id
    from .providers import parse_model_id
    provider, bare_model = parse_model_id(model_id)

    store_usage(
        conversation_id=conversation_id,
        message_id=message_id,
        model=bare_model,
        provider=provider,
        stage=stage,
        usage=usage,
        source=source,
        api_key_id=api_key_id,
    )


def store_stage_usage(
    conversation_id: Optional[str],
    message_id: Optional[str],
    stage: str,
    raw_responses: Dict[str, Any],
    source: str = 'chat',
    api_key_id: Optional[str] = None,
) -> None:
    """Store usage for all model responses in a stage.

    Args:
        conversation_id: The conversation ID (None for API calls)
        message_id: The message ID (None for API calls)
        stage: Stage name (stage1, stage2, stage3)
        raw_responses: Dict of model_id -> full response dict
        source: 'chat' or 'api'
        api_key_id: API key ID for public API calls
    """
    for model_id, response in raw_responses.items():
        store_usage_from_response(
            conversation_id, message_id, model_id, stage, response,
            source=source, api_key_id=api_key_id,
        )


def get_usage_stats(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user_id: Optional[str] = None,
    source: Optional[str] = None,
) -> Dict[str, Any]:
    """Get aggregated usage statistics.

    Args:
        start_date: ISO date string (e.g., "2024-01-01")
        end_date: ISO date string
        user_id: Optional user ID to filter by (requires joining with conversations)
        source: Optional filter by source ('chat', 'api', or None for all)

    Returns:
        Dict with summary stats, provider breakdown, model breakdown, daily stats
    """
    try:
        # uses module-level supabase singleton

        # Build base query
        query = supabase.table("token_usage").select("*")

        if start_date:
            query = query.gte("created_at", start_date)
        if end_date:
            query = query.lte("created_at", end_date)
        if source and source in ('chat', 'api'):
            query = query.eq("source", source)

        # If user_id is provided, we need to join with conversations
        if user_id:
            # First get conversation IDs for this user
            conv_query = supabase.table("conversations").select("id")
            if user_id != "admin":  # admin can see all
                conv_query = conv_query.eq("user_id", user_id)
            conv_response = conv_query.execute()
            conversation_ids = [c["id"] for c in conv_response.data]

            if not conversation_ids:
                return {
                    "summary": {
                        "total_requests": 0,
                        "total_tokens": 0,
                        "total_prompt_tokens": 0,
                        "total_completion_tokens": 0,
                        "total_cached_tokens": 0,
                        "estimated_cost_usd": 0.0,
                    },
                    "by_provider": [],
                    "by_model": [],
                    "by_stage": [],
                    "daily": [],
                }

            query = query.in_("conversation_id", conversation_ids)

        response = query.execute()
        records = response.data

        if not records:
            return {
                "summary": {
                    "total_requests": 0,
                    "total_tokens": 0,
                    "total_prompt_tokens": 0,
                    "total_completion_tokens": 0,
                    "total_cached_tokens": 0,
                    "estimated_cost_usd": 0.0,
                },
                "by_provider": [],
                "by_model": [],
                "by_stage": [],
                "daily": [],
            }

        # Calculate summary stats
        total_requests = len(records)
        total_prompt_tokens = sum(r.get("prompt_tokens", 0) for r in records)
        total_completion_tokens = sum(r.get("completion_tokens", 0) for r in records)
        total_tokens = sum(r.get("total_tokens", 0) for r in records)
        total_cached_tokens = sum(r.get("cached_tokens", 0) for r in records)
        total_cost = sum(r.get("estimated_cost_usd", 0) or 0 for r in records)

        # Provider breakdown
        from collections import defaultdict
        provider_stats = defaultdict(lambda: {
            "requests": 0, "tokens": 0, "prompt_tokens": 0,
            "completion_tokens": 0, "cost": 0.0
        })

        model_stats = defaultdict(lambda: {
            "provider": "", "requests": 0, "tokens": 0,
            "prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0
        })

        stage_stats = defaultdict(lambda: {
            "requests": 0, "tokens": 0, "cost": 0.0
        })

        daily_stats = defaultdict(lambda: {
            "date": "", "requests": 0, "tokens": 0, "cost": 0.0
        })

        for r in records:
            provider = r.get("provider", "unknown")
            model = r.get("model", "unknown")
            stage = r.get("stage", "unknown")
            created_at = r.get("created_at", "")
            tokens = r.get("total_tokens", 0)
            cost = r.get("estimated_cost_usd", 0) or 0

            # Provider stats
            provider_stats[provider]["requests"] += 1
            provider_stats[provider]["tokens"] += tokens
            provider_stats[provider]["prompt_tokens"] += r.get("prompt_tokens", 0)
            provider_stats[provider]["completion_tokens"] += r.get("completion_tokens", 0)
            provider_stats[provider]["cost"] += cost

            # Model stats
            model_stats[model]["provider"] = provider
            model_stats[model]["requests"] += 1
            model_stats[model]["tokens"] += tokens
            model_stats[model]["prompt_tokens"] += r.get("prompt_tokens", 0)
            model_stats[model]["completion_tokens"] += r.get("completion_tokens", 0)
            model_stats[model]["cost"] += cost

            # Stage stats
            stage_stats[stage]["requests"] += 1
            stage_stats[stage]["tokens"] += tokens
            stage_stats[stage]["cost"] += cost

            # Daily stats
            date_key = created_at[:10] if created_at else "unknown"
            daily_stats[date_key]["date"] = date_key
            daily_stats[date_key]["requests"] += 1
            daily_stats[date_key]["tokens"] += tokens
            daily_stats[date_key]["cost"] += cost

        # Convert to sorted lists
        by_provider = [
            {
                "provider": k,
                "requests": v["requests"],
                "tokens": v["tokens"],
                "prompt_tokens": v["prompt_tokens"],
                "completion_tokens": v["completion_tokens"],
                "estimated_cost_usd": round(v["cost"], 6),
            }
            for k, v in sorted(provider_stats.items(), key=lambda x: x[1]["cost"], reverse=True)
        ]

        by_model = [
            {
                "model": k,
                "provider": v["provider"],
                "requests": v["requests"],
                "tokens": v["tokens"],
                "prompt_tokens": v["prompt_tokens"],
                "completion_tokens": v["completion_tokens"],
                "avg_tokens": round(v["tokens"] / v["requests"], 2) if v["requests"] > 0 else 0,
                "estimated_cost_usd": round(v["cost"], 6),
            }
            for k, v in sorted(model_stats.items(), key=lambda x: x[1]["cost"], reverse=True)
        ]

        by_stage = [
            {
                "stage": k,
                "requests": v["requests"],
                "tokens": v["tokens"],
                "estimated_cost_usd": round(v["cost"], 6),
            }
            for k, v in sorted(stage_stats.items(), key=lambda x: x[1]["cost"], reverse=True)
        ]

        daily = [
            {
                "date": k,
                "requests": v["requests"],
                "tokens": v["tokens"],
                "estimated_cost_usd": round(v["cost"], 6),
            }
            for k, v in sorted(daily_stats.items())
        ]

        return {
            "summary": {
                "total_requests": total_requests,
                "total_tokens": total_tokens,
                "total_prompt_tokens": total_prompt_tokens,
                "total_completion_tokens": total_completion_tokens,
                "total_cached_tokens": total_cached_tokens,
                "estimated_cost_usd": round(total_cost, 6),
            },
            "by_provider": by_provider,
            "by_model": by_model,
            "by_stage": by_stage,
            "daily": daily,
            "date_range": {
                "start": start_date,
                "end": end_date,
            },
        }

    except Exception as e:
        logger.error(f"Failed to get usage stats: {e}")
        raise
