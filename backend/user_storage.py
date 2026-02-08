"""Supabase-based storage for users."""

import logging
from typing import Optional, Dict, Any, List
from passlib.context import CryptContext
from .database import supabase

logger = logging.getLogger(__name__)

# Password hashing context using bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(user: Dict[str, Any], password: str) -> bool:
    """Verify a password against a user's password hash."""
    stored_hash = user.get("password_hash", "")
    return pwd_context.verify(password, stored_hash)


def create_user(username: str, email: str, password: str) -> Dict[str, Any]:
    """Create a new user."""
    # Check if username or email already exists
    if get_user_by_username(username):
        raise ValueError(f"Username {username} already exists")
    if get_user_by_email(email):
        raise ValueError(f"Email {email} already exists")

    user_data = {
        "username": username,
        "email": email,
        "password_hash": hash_password(password),
        "is_active": True,
        "is_admin": False,
    }

    result = supabase.table("users").insert(user_data).execute()
    return result.data[0]


def get_user(user_id: str) -> Optional[Dict[str, Any]]:
    """Load a user by ID."""
    result = supabase.table("users").select("*").eq("id", user_id).execute()
    if result.data:
        return result.data[0]
    return None


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Get a user by username."""
    result = supabase.table("users").select("*").eq("username", username).execute()
    if result.data:
        return result.data[0]
    return None


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Get a user by email."""
    result = supabase.table("users").select("*").eq("email", email).execute()
    if result.data:
        return result.data[0]
    return None


def list_all_users() -> List[Dict[str, Any]]:
    """List all users (for admin). Does not include password hash."""
    result = (
        supabase.table("users")
        .select("id,username,email,created_at,is_active")
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


def delete_user(user_id: str) -> bool:
    """Delete a user."""
    result = supabase.table("users").delete().eq("id", user_id).execute()
    return len(result.data) > 0


def reset_user_password(user_id: str, new_password: str) -> bool:
    """Reset a user's password."""
    result = (
        supabase.table("users")
        .update({"password_hash": hash_password(new_password)})
        .eq("id", user_id)
        .execute()
    )
    return len(result.data) > 0
