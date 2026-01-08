"""JSON-based storage for users."""

import json
import os
import hashlib
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path
from .config import USER_DATA_DIR


def ensure_user_dir():
    """Ensure the user data directory exists."""
    Path(USER_DATA_DIR).mkdir(parents=True, exist_ok=True)


def get_user_path(user_id: str) -> str:
    """Get the file path for a user."""
    return os.path.join(USER_DATA_DIR, f"{user_id}.json")


def hash_password(password: str) -> str:
    """Hash a password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()


def create_user(username: str, email: str, password: str) -> Dict[str, Any]:
    """
    Create a new user.

    Args:
        username: Username
        email: Email address
        password: Plain text password (will be hashed)

    Returns:
        New user dict
    """
    ensure_user_dir()

    # Check if username or email already exists
    if get_user_by_username(username):
        raise ValueError(f"Username {username} already exists")
    if get_user_by_email(email):
        raise ValueError(f"Email {email} already exists")

    user_id = str(datetime.utcnow().timestamp()).replace('.', '')
    user = {
        "id": user_id,
        "username": username,
        "email": email,
        "password_hash": hash_password(password),
        "created_at": datetime.utcnow().isoformat(),
        "is_active": True
    }

    # Save to file
    path = get_user_path(user_id)
    with open(path, 'w') as f:
        json.dump(user, f, indent=2)

    return user


def get_user(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Load a user from storage.

    Args:
        user_id: Unique identifier for the user

    Returns:
        User dict or None if not found
    """
    path = get_user_path(user_id)

    if not os.path.exists(path):
        return None

    with open(path, 'r') as f:
        return json.load(f)


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Get a user by username."""
    ensure_user_dir()

    for filename in os.listdir(USER_DATA_DIR):
        if filename.endswith('.json'):
            path = os.path.join(USER_DATA_DIR, filename)
            with open(path, 'r') as f:
                user = json.load(f)
                if user.get("username") == username:
                    return user
    return None


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Get a user by email."""
    ensure_user_dir()

    for filename in os.listdir(USER_DATA_DIR):
        if filename.endswith('.json'):
            path = os.path.join(USER_DATA_DIR, filename)
            with open(path, 'r') as f:
                user = json.load(f)
                if user.get("email") == email:
                    return user
    return None


def verify_password(user: Dict[str, Any], password: str) -> bool:
    """Verify a password against a user's password hash."""
    password_hash = hash_password(password)
    return user.get("password_hash") == password_hash

