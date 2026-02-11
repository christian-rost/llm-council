"""App settings stored in Supabase."""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from .database import supabase
from .config import COUNCIL_MODELS as DEFAULT_COUNCIL, CHAIRMAN_MODEL as DEFAULT_CHAIRMAN
from .providers.base import PROVIDER_CONFIGS, encrypt_value, decrypt_value

logger = logging.getLogger(__name__)


def get_setting(key: str, default=None):
    """Read a setting from the app_settings table."""
    result = supabase.table("app_settings").select("value").eq("key", key).execute()
    if result.data:
        return result.data[0]["value"]
    return default


def set_setting(key: str, value):
    """Set a setting in app_settings (upsert)."""
    supabase.table("app_settings").upsert(
        {"key": key, "value": value, "updated_at": datetime.now(timezone.utc).isoformat()},
        on_conflict="key"
    ).execute()


def get_chairman_model() -> str:
    return get_setting("chairman_model", DEFAULT_CHAIRMAN)


def get_council_models() -> list:
    return get_setting("council_models", DEFAULT_COUNCIL)


def get_web_search_enabled() -> bool:
    """Check if web search is enabled (default: False)."""
    return get_setting("web_search_enabled", False)


def set_web_search_enabled(enabled: bool) -> None:
    """Enable or disable web search."""
    set_setting("web_search_enabled", enabled)


# ── Provider API Key Management ─────────────────────────────────────────────

def get_provider_api_key(provider: str) -> Optional[str]:
    """Get decrypted API key for a provider from DB. Returns None if not found."""
    try:
        result = (
            supabase.table("provider_api_keys")
            .select("api_key_encrypted, is_active")
            .eq("provider", provider)
            .execute()
        )
        if result.data and result.data[0].get("is_active"):
            return decrypt_value(result.data[0]["api_key_encrypted"])
    except Exception as e:
        logger.error(f"Error reading provider key for '{provider}': {e}")
    return None


def set_provider_api_key(provider: str, api_key: str) -> None:
    """Encrypt and upsert an API key for a provider."""
    encrypted = encrypt_value(api_key)
    supabase.table("provider_api_keys").upsert(
        {
            "provider": provider,
            "api_key_encrypted": encrypted,
            "is_active": True,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="provider",
    ).execute()


def delete_provider_api_key(provider: str) -> bool:
    """Delete (deactivate) a provider API key."""
    result = (
        supabase.table("provider_api_keys")
        .update({"is_active": False, "updated_at": datetime.now(timezone.utc).isoformat()})
        .eq("provider", provider)
        .execute()
    )
    return bool(result.data)


def get_all_provider_keys_status() -> list[dict]:
    """Return status of all providers (name, configured, source). Never returns actual keys."""
    # Get all DB keys (just provider + is_active)
    try:
        db_result = (
            supabase.table("provider_api_keys")
            .select("provider, is_active")
            .execute()
        )
        db_keys = {row["provider"]: row["is_active"] for row in (db_result.data or [])}
    except Exception:
        db_keys = {}

    statuses = []
    for provider_id, config in PROVIDER_CONFIGS.items():
        env_key = os.getenv(config["env_var"])
        has_env = bool(env_key)
        has_db = db_keys.get(provider_id, False)

        if has_db:
            source = "database"
        elif has_env:
            source = "environment"
        else:
            source = "not_configured"

        statuses.append({
            "provider": provider_id,
            "name": config["name"],
            "configured": has_db or has_env,
            "source": source,
        })

    return statuses
