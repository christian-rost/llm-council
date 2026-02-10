"""API Key management for the public REST API."""

import secrets
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

import bcrypt

from .database import supabase

logger = logging.getLogger(__name__)

KEY_PREFIX = "xqt5-"


def generate_api_key() -> str:
    """Generate a new API key with xqt5- prefix + 48 hex chars."""
    return KEY_PREFIX + secrets.token_hex(24)


def _hash_key(api_key: str) -> str:
    """Hash an API key using bcrypt."""
    return bcrypt.hashpw(api_key.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def _get_key_prefix(api_key: str) -> str:
    """Extract a storable prefix from an API key for lookup (first 12 chars)."""
    return api_key[:12]


def create_api_key(name: str, rate_limit: int = 5) -> Dict[str, Any]:
    """
    Create a new API key.

    Returns the full key info including the plaintext key (only returned once).
    """
    plaintext_key = generate_api_key()

    row = {
        "name": name,
        "key_hash": _hash_key(plaintext_key),
        "key_prefix": _get_key_prefix(plaintext_key),
        "is_active": True,
        "rate_limit": rate_limit,
        "usage_count": 0,
    }

    result = supabase.table("api_keys").insert(row).execute()
    record = result.data[0]

    return {
        "id": record["id"],
        "name": record["name"],
        "key": plaintext_key,
        "key_prefix": record["key_prefix"],
        "rate_limit": record["rate_limit"],
        "created_at": record["created_at"],
    }


def verify_api_key(api_key: str) -> Optional[Dict[str, Any]]:
    """
    Verify an API key. Returns the key record if valid, None otherwise.

    Uses prefix lookup + bcrypt verify for security.
    Updates last_used_at and usage_count on success.
    """
    if not api_key or not api_key.startswith(KEY_PREFIX):
        return None

    prefix = _get_key_prefix(api_key)

    try:
        result = (
            supabase.table("api_keys")
            .select("*")
            .eq("key_prefix", prefix)
            .eq("is_active", True)
            .execute()
        )
    except Exception as e:
        logger.error(f"Error looking up API key: {e}")
        return None

    for record in result.data:
        try:
            if bcrypt.checkpw(api_key.encode("utf-8")[:72], record["key_hash"].encode("utf-8")):
                # Update usage stats
                try:
                    supabase.table("api_keys").update({
                        "last_used_at": datetime.now(timezone.utc).isoformat(),
                        "usage_count": record["usage_count"] + 1,
                    }).eq("id", record["id"]).execute()
                except Exception as e:
                    logger.warning(f"Failed to update API key usage stats: {e}")

                return record
        except Exception:
            continue

    return None


def list_api_keys() -> List[Dict[str, Any]]:
    """List all API keys (without hashes)."""
    result = (
        supabase.table("api_keys")
        .select("id,name,key_prefix,is_active,rate_limit,usage_count,created_at,last_used_at")
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


def delete_api_key(key_id: str) -> bool:
    """Soft-delete an API key by setting is_active=False."""
    try:
        result = (
            supabase.table("api_keys")
            .update({"is_active": False})
            .eq("id", key_id)
            .execute()
        )
        return len(result.data) > 0
    except Exception as e:
        logger.error(f"Error deleting API key: {e}")
        return False
