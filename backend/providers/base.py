"""Provider configuration and encryption helpers."""

import base64
import hashlib
import json
import logging

import httpx
from cryptography.fernet import Fernet, InvalidToken

from ..config import JWT_SECRET

logger = logging.getLogger(__name__)

# Max length of a provider error reason shown to users
MAX_ERROR_DETAIL = 300


class ProviderError(Exception):
    """A provider request failed. The message is a short, user-safe reason."""


def format_http_error(status_code: int, body: str) -> str:
    """Build a compact reason from an HTTP error response body."""
    detail = ""
    try:
        data = json.loads(body)
        error = data.get("error", data) if isinstance(data, dict) else data
        if isinstance(error, dict):
            detail = error.get("message") or error.get("detail") or ""
        elif isinstance(error, str):
            detail = error
    except (ValueError, TypeError):
        detail = ""

    if not detail:
        detail = body

    detail = " ".join(str(detail).split())[:MAX_ERROR_DETAIL]
    return f"HTTP {status_code}: {detail}" if detail else f"HTTP {status_code}"


def format_exception(exc: Exception) -> str:
    """Build a compact reason from an exception raised while querying."""
    if isinstance(exc, httpx.TimeoutException):
        return "Timeout: provider did not respond in time"
    if isinstance(exc, httpx.HTTPError):
        return f"Network error: {exc.__class__.__name__}"

    detail = " ".join(str(exc).split())[:MAX_ERROR_DETAIL]
    return f"{exc.__class__.__name__}: {detail}" if detail else exc.__class__.__name__

# Provider configurations: name, base URL, env var for API key
PROVIDER_CONFIGS = {
    "openrouter": {
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1/chat/completions",
        "env_var": "OPENROUTER_API_KEY",
    },
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1/chat/completions",
        "env_var": "OPENAI_API_KEY",
    },
    "google": {
        "name": "Google (Gemini)",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "env_var": "GOOGLE_API_KEY",
    },
    "anthropic": {
        "name": "Anthropic",
        "base_url": "https://api.anthropic.com/v1/messages",
        "env_var": "ANTHROPIC_API_KEY",
    },
    "xai": {
        "name": "xAI (Grok)",
        "base_url": "https://api.x.ai/v1/chat/completions",
        "env_var": "XAI_API_KEY",
    },
    "mistral": {
        "name": "Mistral",
        "base_url": "https://api.mistral.ai/v1/chat/completions",
        "env_var": "MISTRAL_API_KEY",
    },
}


def _get_fernet() -> Fernet:
    """Derive a Fernet key from JWT_SECRET."""
    key = hashlib.sha256(JWT_SECRET.encode()).digest()
    fernet_key = base64.urlsafe_b64encode(key)
    return Fernet(fernet_key)


def encrypt_value(plaintext: str) -> str:
    """Encrypt a string value using Fernet (derived from JWT_SECRET)."""
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str | None:
    """Decrypt a Fernet-encrypted string. Returns None on failure."""
    try:
        f = _get_fernet()
        return f.decrypt(ciphertext.encode()).decode()
    except (InvalidToken, Exception) as e:
        logger.error(f"Decryption failed: {e}")
        return None
