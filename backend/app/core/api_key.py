"""API key utilities for device authentication."""

import hashlib
import secrets

from .config import settings


def generate_api_key() -> str:
    """
    Generate a new random API key.

    Returns:
        A secure random API key (64 characters hex)
    """
    return secrets.token_hex(32)


def hash_api_key(api_key: str) -> str:
    """
    Hash an API key for storage in the database.

    Uses HMAC-SHA256 with salt from settings to prevent rainbow table attacks.

    Args:
        api_key: Plain API key

    Returns:
        Hashed API key
    """
    salted = f"{api_key}{settings.api_key_salt}"
    return hashlib.sha256(salted.encode()).hexdigest()


def verify_api_key(plain_key: str, hashed_key: str) -> bool:
    """
    Verify an API key against a stored hash.

    Args:
        plain_key: Plain API key from request
        hashed_key: Hashed API key from database

    Returns:
        True if key matches, False otherwise
    """
    return hash_api_key(plain_key) == hashed_key
