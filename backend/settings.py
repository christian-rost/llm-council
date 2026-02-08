"""App settings stored in Supabase."""

from datetime import datetime, timezone
from .database import supabase
from .config import COUNCIL_MODELS as DEFAULT_COUNCIL, CHAIRMAN_MODEL as DEFAULT_CHAIRMAN


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
